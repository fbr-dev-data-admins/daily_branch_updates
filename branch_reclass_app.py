"""Streamlit tool for RE query 40677 branch reclassification."""

import base64
import hmac
import json
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from io import BytesIO
from urllib.parse import quote, urlparse

import pandas as pd
import requests
import streamlit as st
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils.dataframe import dataframe_to_rows

from re_skyapi import API_BASE_URL, RESkyAPI


QUERY_ID = "40677"
FORCE_IN_QUERY_ID = "40737"

QUERY_COLUMNS = [
    "GFImpID",
    "GFAttrImpID",
    "GFAttrDesc",
    "Gift Reference",
    "EN Donation Form Name",
    "Gift Date Added",
    "Gift Added By",
    "Constituent ID",
    "Name",
    "Preferred State",
    "Preferred ZIP",
    "Monthly Donor Region",
    "Package ID",
    "Appeal ID",
]

WSLOPE_REGION_ZIP_PREFIXES = [
    "814", "815", "816",
    "80423", "80424", "80426", "80428", "80429", "80435", "80443",
    "80461", "80463", "80467", "80469", "80477", "80478", "80479",
    "80483", "80487", "80488", "80497", "80498",
    "81220", "81251", "81325",
]


def check_password() -> bool:
    """Show the app only after the configured password has been entered."""

    def password_entered():
        entered_password = st.session_state.pop("password", "")
        configured_password = str(st.secrets["app"]["password"])
        st.session_state["password_correct"] = hmac.compare_digest(
            entered_password, configured_password
        )

    if "password_correct" not in st.session_state:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        return False
    if not st.session_state["password_correct"]:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("Password incorrect")
        return False
    return True


def clean_string(value) -> str:
    """Return a stripped string, treating pandas missing values as blank."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def zip_matches_wslope(zip_val: str) -> bool:
    zip_val = clean_string(zip_val)
    return any(zip_val.startswith(prefix) for prefix in WSLOPE_REGION_ZIP_PREFIXES)


def get_re_client() -> RESkyAPI:
    """Build an auth client backed exclusively by this Streamlit session."""
    return RESkyAPI(
        client_id=st.secrets["re_api"]["client_id"],
        client_secret=st.secrets["re_api"]["client_secret"],
        redirect_uri=st.secrets["re_api"]["redirect_uri"],
        subscription_key=st.secrets["re_api"]["subscription_key"],
        session_state=st.session_state,
    )


def start_query(query_id: str) -> str:
    url = f"{API_BASE_URL}/query/queries/executebyid?product=RE&module=None"
    payload = {
        "id": int(query_id),
        "ux_mode": "Asynchronous",
        "output_format": "Json",
        "formatting_mode": "Export",
        "sql_generation_mode": "Query",
    }
    resp = requests.post(url, headers=get_re_client().get_headers(), json=payload)
    resp.raise_for_status()
    return resp.json()["id"]


def poll_status(job_id: str) -> str:
    url = (
        f"{API_BASE_URL}/query/jobs/{job_id}"
        "?product=RE&module=None&include_read_url=OnceCompleted"
    )
    time.sleep(10)
    for _attempt in range(60):
        resp = requests.get(url, headers=get_re_client().get_headers())
        resp.raise_for_status()
        data = resp.json()
        status = (data.get("status") or "").lower()
        if status == "completed":
            sas_uri = data.get("sas_uri")
            if not sas_uri:
                raise RuntimeError("Job completed but no sas_uri returned.")
            return sas_uri
        if status in ("failed", "error", "cancelled"):
            raise RuntimeError(f"Query job ended with status '{status}'.")
        time.sleep(5)
    raise RuntimeError("Timed out polling query 40677.")


def fetch_results(sas_uri: str) -> list:
    resp = requests.get(sas_uri)  # The pre-signed SAS URI must have no auth headers.
    resp.raise_for_status()
    return resp.json()


def run_saved_query(query_id: str) -> pd.DataFrame:
    job_id = start_query(query_id)
    sas_uri = poll_status(job_id)
    return pd.DataFrame(fetch_results(sas_uri))


def run_query_40677() -> pd.DataFrame:
    return run_saved_query(QUERY_ID)


def github_repo_parts() -> tuple[str, str]:
    parsed = urlparse(st.secrets["github"]["config_repo"].rstrip("/"))
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("github.config_repo must be a GitHub repository URL.")
    return parts[0], parts[1]


def github_headers() -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {st.secrets['github']['access_token']}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_contents_url() -> str:
    owner, repo = github_repo_parts()
    path = quote(str(st.secrets["github"]["cache_path"]).lstrip("/"), safe="/")
    return f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"


def load_config_from_github() -> dict:
    response = requests.get(github_contents_url(), headers=github_headers())
    if response.status_code == 404:
        return {"run_dates": {}}
    response.raise_for_status()
    payload = response.json()
    content = payload.get("content", "")
    if not content.strip():
        return {"run_dates": {}}
    config = json.loads(base64.b64decode(content).decode("utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("run_dates", {}), dict):
        raise ValueError("The GitHub run cache has an invalid format.")
    config.setdefault("run_dates", {})
    return config


def push_config_to_github(config: dict) -> None:
    url = github_contents_url()
    current = requests.get(url, headers=github_headers())
    sha = None
    if current.status_code != 404:
        current.raise_for_status()
        sha = current.json().get("sha")
    body = {
        "message": "Update branch reclassification run cache",
        "content": base64.b64encode(
            (json.dumps(config, indent=2, sort_keys=True) + "\n").encode("utf-8")
        ).decode("ascii"),
    }
    if sha:
        body["sha"] = sha
    response = requests.put(url, headers=github_headers(), json=body)
    response.raise_for_status()


def build_calendar_preview(run_dates: dict, weeks_back: int = 4) -> pd.DataFrame:
    today = datetime.today().date()
    current_sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    start = current_sunday - timedelta(weeks=weeks_back - 1)
    weeks = []
    for week in range(weeks_back):
        row = []
        for weekday in range(7):
            day = start + timedelta(days=week * 7 + weekday)
            marker = "✅" if day.isoformat() in run_dates else ""
            row.append(f"{day.strftime('%b')} {day.day}{marker}")
        weeks.append(row)
    return pd.DataFrame(weeks, columns=["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])


def previous_business_date(today: date | None = None) -> date:
    """Return the most recent weekday before today."""
    candidate = (today or datetime.today().date()) - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def evaluate_rules(row: pd.Series) -> list[tuple[str, str]]:
    """Return proposals from only the highest-priority matching rule category.

    ZIP/state and Monthly Donor Region deliberately share one priority category,
    so disagreement between those signals remains visible as a rule conflict.
    """
    branch = clean_string(row["GFAttrDesc"])
    state = clean_string(row["Preferred State"])
    donor_region = clean_string(row["Monthly Donor Region"])
    gift_reference = clean_string(row["Gift Reference"])
    form_name = clean_string(row["EN Donation Form Name"])
    package_id = clean_string(row["Package ID"])
    appeal_id = clean_string(row["Appeal ID"])
    categories: list[list[tuple[str, str]]] = []

    # 1. Appeal/package assignments to Main.
    appeal_package = []
    if branch != "Main" and (
        package_id in ["Serv", "Ardent"]
        or appeal_id.endswith("GS")
        or appeal_id.endswith("GOLF")
    ):
        appeal_package.append(("Event", "Main"))
    categories.append(appeal_package)

    # 2. Wyo Gives.
    wyo_gives = []
    if branch != "Wyoming" and appeal_id.endswith("WYOG"):
        wyo_gives.append(("Wyo Gives", "Wyoming"))
    categories.append(wyo_gives)

    # 3. Gift Reference.
    gift_reference_rules = []
    reference_lower = gift_reference.lower()
    if branch == "Main" and ("wslope" in reference_lower or "western slope" in reference_lower):
        gift_reference_rules.append(("Gift Reference", "WSlope"))
    if branch == "Main" and ("wyoming" in reference_lower or "wyo" in reference_lower):
        gift_reference_rules.append(("Gift Reference", "Wyoming"))
    categories.append(gift_reference_rules)

    # 4. EN donation form name.
    donation_form = []
    if branch == "Main" and form_name.startswith("S"):
        donation_form.append(("EN Donation Form Name", "WSlope"))
    if branch == "Main" and form_name.startswith("Y"):
        donation_form.append(("EN Donation Form Name", "Wyoming"))
    categories.append(donation_form)

    # 5. Regional ZIP/state and Monthly Donor Region share a priority tier.
    regional = []
    if branch == "Main" and zip_matches_wslope(row["Preferred ZIP"]):
        regional.append(("ZIP/State Update", "WSlope"))
    if branch == "Main" and state == "Wyoming":
        regional.append(("ZIP/State Update", "Wyoming"))
    if branch == "Main" and donor_region == "Western Slope":
        regional.append(("Monthly Donor Region", "WSlope"))
    if branch == "Main" and donor_region == "Wyoming":
        regional.append(("Monthly Donor Region", "Wyoming"))
    categories.append(regional)

    for proposals in categories:
        if proposals:
            return list(dict.fromkeys(proposals))
    return []


def conflict_rule_flag(proposals: list[tuple[str, str]]) -> str:
    details = " vs ".join(f"{target} via {reason}" for reason, target in proposals)
    return f"Conflict: rules disagree ({details})"


def classify_rows(
    df: pd.DataFrame, force_in_constituent_ids: set[str] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split deduplicated rows into import, review, no-change, and conflict sets."""
    force_in_constituent_ids = force_in_constituent_ids or set()
    records = []
    for index, row in df.reset_index(drop=True).iterrows():
        original_branch = clean_string(row["GFAttrDesc"])
        force_in = clean_string(row["Constituent ID"]) in force_in_constituent_ids
        if force_in:
            # Force-In is evaluated first and completely replaces all ordinary rule
            # proposals for the row, so ordinary rule conflicts cannot supersede it.
            proposals = [("WSlope Force-In", "WSlope")]
            clean_change = original_branch != "WSlope"
            final_branch = "WSlope"
            flag = ""
        else:
            proposals = evaluate_rules(row)
            targets = {target for _reason, target in proposals}
            clean_change = len(targets) == 1 and next(iter(targets)) != original_branch
            final_branch = next(iter(targets)) if clean_change else original_branch
            flag = conflict_rule_flag(proposals) if len(targets) > 1 else ""
        records.append(
            {
                "index": index,
                "proposals": proposals,
                "clean_change": clean_change,
                "final_branch": final_branch,
                "flag": flag,
            }
        )

    # A blank GFImpID is still a value: repeated blank IDs with differing final branches
    # meet the stated same-GFImpID conflict rule.
    by_gfimpid = {}
    for record in records:
        gfimpid = clean_string(df.reset_index(drop=True).at[record["index"], "GFImpID"])
        by_gfimpid.setdefault(gfimpid, []).append(record)
    for gfimpid, grouped in by_gfimpid.items():
        if len(grouped) > 1 and len({item["final_branch"] for item in grouped}) > 1:
            note = f"Conflict: GFImpID {gfimpid} has differing final branch across rows"
            for item in grouped:
                item["flag"] = f"{item['flag']}; {note}" if item["flag"] else note
                item["clean_change"] = False

    source = df.reset_index(drop=True)
    import_rows = []
    review_rows = []
    no_change_rows = []
    conflict_rows = []
    for record in records:
        row = source.loc[record["index"]].copy()
        if record["clean_change"] and not record["flag"]:
            reasons = list(dict.fromkeys(reason for reason, _target in record["proposals"]))
            row["Original Branch"] = clean_string(row["GFAttrDesc"])
            row["GFAttrDesc"] = record["final_branch"]
            row["Reason"] = "; ".join(reasons)
            import_rows.append(row)
            continue

        gift_reference = clean_string(row["Gift Reference"])
        state = clean_string(row["Preferred State"])
        branch = clean_string(row["GFAttrDesc"])
        form_name = clean_string(row["EN Donation Form Name"])
        donor_region = clean_string(row["Monthly Donor Region"])
        colorado_review = (
            state == "Colorado"
            and branch != "Main"
            and form_name.startswith("D")
            and (not zip_matches_wslope(row["Preferred ZIP"]) or donor_region == "Denver")
        )
        review_flags = []
        if record["flag"]:
            review_flags.append(record["flag"])
        if gift_reference:
            review_flags.append("Review: Gift Reference contains text")
        if colorado_review:
            review_flags.append(
                "Review: Colorado non-Main record may need branch reassignment"
            )
        row["Flag"] = "; ".join(review_flags)
        if review_flags:
            review_rows.append(row)
        else:
            no_change_rows.append(row)
        if record["flag"]:
            conflict_rows.append(row)

    import_columns = list(df.columns) + ["Original Branch", "Reason"]
    non_import_columns = list(df.columns) + ["Flag"]
    return (
        pd.DataFrame(import_rows, columns=import_columns),
        pd.DataFrame(review_rows, columns=non_import_columns),
        pd.DataFrame(no_change_rows, columns=non_import_columns),
        pd.DataFrame(conflict_rows, columns=non_import_columns),
    )


def build_review_workbook(review_df: pd.DataFrame, no_change_df: pd.DataFrame) -> bytes:
    output = BytesIO()
    workbook = Workbook()
    default_sheet = workbook.active
    workbook.remove(default_sheet)
    for sheet_name, frame in (("review", review_df), ("no_change", no_change_df)):
        sheet = workbook.create_sheet(sheet_name)
        # Object conversion ensures pandas NaN/NA values become valid blank Excel cells.
        excel_frame = frame.astype(object).where(pd.notna(frame), None)
        for row in dataframe_to_rows(excel_frame, index=False, header=True):
            sheet.append(row)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
    workbook.save(output)
    return output.getvalue()


def record_download(start_date: date, end_date: date, rows_changed: int) -> None:
    """Download-button callback: write one run entry for every selected date."""
    try:
        cache = deepcopy(st.session_state.get("run_cache", {"run_dates": {}}))
        run_dates = cache.setdefault("run_dates", {})
        entry = {
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "rows_changed": rows_changed,
        }
        day = start_date
        while day <= end_date:
            run_dates.setdefault(day.isoformat(), []).append(dict(entry))
            day += timedelta(days=1)
        push_config_to_github(cache)
        st.session_state.run_cache = cache
        st.session_state.cache_notice = "Run dates saved to GitHub."
    except Exception as exc:  # Surface remote-cache failures without breaking the download.
        st.session_state.cache_error = f"Could not update the GitHub run cache: {exc}"


def render_auth_sidebar() -> bool:
    st.sidebar.header("Raiser's Edge NXT Authentication")
    client = get_re_client()
    try:
        authenticated = client.is_authenticated()
    except Exception as exc:
        authenticated = False
        st.sidebar.error(f"Authentication refresh failed: {exc}")
    if authenticated:
        st.sidebar.success("Authenticated with Raiser's Edge NXT")
        return True

    st.sidebar.warning("Not authenticated with Raiser's Edge NXT")
    if st.sidebar.button("Get Authorization URL"):
        st.session_state.re_authorization_url = client.get_authorization_url()
    if st.session_state.get("re_authorization_url"):
        st.sidebar.markdown(
            f"[Open the Blackbaud authorization page]({st.session_state.re_authorization_url})"
        )
    auth_code = st.sidebar.text_input("Paste authorization code", key="re_auth_code")
    if st.sidebar.button("Submit Authorization Code"):
        if not auth_code.strip():
            st.sidebar.error("Paste an authorization code first.")
        else:
            try:
                client.exchange_code_for_token(auth_code.strip())
                st.rerun()
            except Exception as exc:
                st.sidebar.error(f"Authorization failed: {exc}")
    return False


def render_app() -> None:
    st.title("Daily Branch Reclassification Tool")
    authenticated = render_auth_sidebar()

    if "run_cache" not in st.session_state:
        try:
            st.session_state.run_cache = load_config_from_github()
        except Exception as exc:
            st.error(f"Could not load the GitHub run cache: {exc}")
            st.session_state.run_cache = {"run_dates": {}}
    if st.session_state.pop("cache_notice", None):
        st.success("Run dates saved to GitHub.")
    cache_error = st.session_state.pop("cache_error", None)
    if cache_error:
        st.error(cache_error)

    st.subheader("Recent run dates")
    st.caption("✅ indicates a previously processed date.")
    st.table(build_calendar_preview(st.session_state.run_cache.get("run_dates", {})))
    st.caption(
        "If you need to process dates further than one week back, the saved query "
        "criteria must be temporarily updated."
    )

    default_date = previous_business_date()
    date_columns = st.columns(2)
    start_date = date_columns[0].date_input(
        "Start date", value=default_date, format="MM/DD/YYYY"
    )
    end_date = date_columns[1].date_input(
        "End date", value=default_date, format="MM/DD/YYYY"
    )

    if not FORCE_IN_QUERY_ID.strip():
        st.info(
            "Set FORCE_IN_QUERY_ID near the top of branch_reclass_app.py before running; "
            "it must identify the saved query containing WSlope Force-In Constituent IDs."
        )

    if st.button(
        "Retrieve data",
        disabled=not authenticated or not FORCE_IN_QUERY_ID.strip(),
    ):
        try:
            with st.spinner("Retrieving branch and WSlope Force-In data..."):
                st.session_state.query_40677_results = run_query_40677()
                st.session_state.force_in_query_results = run_saved_query(FORCE_IN_QUERY_ID)
        except Exception as exc:
            # Do not retain one query's fresh results when the paired run fails.
            st.session_state.pop("query_40677_results", None)
            st.session_state.pop("force_in_query_results", None)
            st.error(f"Query execution failed: {exc}")

    if (
        "query_40677_results" not in st.session_state
        or "force_in_query_results" not in st.session_state
    ):
        return

    raw_df = st.session_state.query_40677_results.copy()
    force_in_df = st.session_state.force_in_query_results.copy()
    missing = [column for column in QUERY_COLUMNS if column not in raw_df.columns]
    if missing:
        st.error(f"Query results are missing required columns: {', '.join(missing)}")
        return
    if "Constituent ID" not in force_in_df.columns:
        st.error("The WSlope Force-In query results are missing required column: Constituent ID")
        return
    force_in_constituent_ids = {
        clean_string(value)
        for value in force_in_df["Constituent ID"]
        if clean_string(value)
    }
    if start_date > end_date:
        st.error("The start date must not be after the end date.")
        return
    parsed_dates = pd.to_datetime(raw_df["Gift Date Added"], errors="coerce")
    date_mask = parsed_dates.dt.date.between(start_date, end_date, inclusive="both")
    filtered_df = raw_df.loc[date_mask].copy()
    deduped_df = filtered_df.drop_duplicates().reset_index(drop=True)
    import_df, review_df, no_change_df, conflicts_df = classify_rows(
        deduped_df, force_in_constituent_ids
    )

    metric_values = [
        ("Total fetched", len(raw_df)),
        ("After date filter", len(filtered_df)),
        ("After dedup", len(deduped_df)),
        ("Import", len(import_df)),
        ("Review", len(review_df)),
        ("No change", len(no_change_df)),
    ]
    for column, (label, value) in zip(st.columns(6), metric_values):
        column.metric(label, value)

    if not conflicts_df.empty:
        st.warning(f"{len(conflicts_df)} conflicting row(s) require manual review.")
        conflict_preview_columns = ["GFImpID", "Name", "GFAttrDesc", "Flag"]
        st.dataframe(conflicts_df[conflict_preview_columns], width="stretch")

    st.subheader("Review sheet preview")
    st.dataframe(review_df, width="stretch", hide_index=True)
    st.subheader("Import preview")
    st.dataframe(import_df.head(20), width="stretch", hide_index=True)
    st.subheader("No-change preview")
    st.dataframe(no_change_df.head(20), width="stretch", hide_index=True)

    csv_bytes = import_df.to_csv(index=False).encode("utf-8")
    workbook_bytes = build_review_workbook(review_df, no_change_df)
    download_columns = st.columns(2)
    download_columns[0].download_button(
        "Download Import CSV",
        data=csv_bytes,
        file_name=f"branch_reclass_import_{start_date}_{end_date}.csv",
        mime="text/csv",
        on_click=record_download,
        args=(start_date, end_date, len(import_df)),
    )
    download_columns[1].download_button(
        "Download Review/No-Change Workbook",
        data=workbook_bytes,
        file_name=f"branch_reclass_review_{start_date}_{end_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if check_password():
    render_app()
