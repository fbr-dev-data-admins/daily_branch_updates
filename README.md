# Daily Branch Updates

## What this app does

This Streamlit app helps staff review recent gifts and assign each one to the most appropriate regional branch. It retrieves gift records from Raiser's Edge NXT, applies the organization's agreed-upon rules in a consistent order, and prepares files for staff to review and use. It does **not** automatically update Raiser's Edge.

In everyday terms, the process is:

1. A staff member signs in to the app with the shared app password.
2. The staff member connects to Raiser's Edge NXT and chooses the dates to process.
3. The app retrieves the saved gift query and a separate list of people who must be assigned to Western Slope.
4. It keeps gifts added during the selected dates and removes exact duplicate rows.
5. It evaluates the assignment rules below, using the first applicable category.
6. It separates the results into records ready to import, records requiring review, and records needing no change.
7. Staff download the files. Downloading the import file also records the processed dates in a GitHub-hosted run history, which supplies the check marks on the app's calendar.

## Branch assignment logic

Rules are considered in this priority order:

1. **Special event identifiers:** Service (`Serv`) or Ardent packages, or appeal identifiers ending in `GS` or `GOLF`, go to **Main**.
2. **Wyoming Gives:** Appeal identifiers ending in `WYOG` go to **Wyoming**.
3. **Gift notes:** A gift currently assigned to Main moves to **Western Slope** when its reference mentions `wslope` or `western slope`, or to **Wyoming** when it mentions `wyoming` or `wyo`.
4. **Western Slope force-in list:** A constituent on this list has a proposed branch of **Western Slope**.
5. **Online donation form:** A gift currently assigned to Main moves to **Western Slope** when the form name begins with `S`, or to **Wyoming** when it begins with `Y`.
6. **Location and monthly-donor region:** A gift currently assigned to Main can move to **Western Slope** based on one of the configured Colorado ZIP-code prefixes or a Western Slope monthly-donor region. It can move to **Wyoming** based on its state or monthly-donor region.

Only one priority category is used for each gift. When signals within that category disagree, the gift is flagged instead of being changed automatically. The app also flags repeated gift import IDs when their rows would end with different branches. Records with gift-reference text and certain Colorado records are placed in the review file even when they do not produce an automatic change, so a person can verify them.

## Output files

* **Import CSV:** Contains clear branch changes. It preserves the original branch and states which rule caused the change. For an appeal identifier ending in `WORK`, the reason also reminds staff to ensure the matching gift receives a branch update.
* **Review workbook:** Contains a `review` sheet for records that deserve attention and a `no_change` sheet for the remaining records. Every review row explains why it needs attention in the `Flag` column, including conflicts, gift-reference text, and Colorado branch checks.

## Configuration and password protection

The app is password protected. Nothing beyond the password prompt is rendered until the value entered matches `[app].password` in `.streamlit/secrets.toml`. The entered password is removed from the user's session immediately after it is checked.

Before running the app, edit `.streamlit/secrets.toml` and replace every placeholder. The file includes settings for:

* the app password;
* the Raiser's Edge NXT / Blackbaud API connection; and
* the GitHub repository, access token, and JSON path used to retain run history.

The committed file is a template only. Do not commit real passwords, client secrets, subscription keys, or access tokens to a public repository. For a hosted Streamlit deployment, copy the same TOML settings into the platform's secrets configuration.

### GitHub fine-grained personal access token

The GitHub token only needs access to the repository named by `github.config_repo`. When creating a fine-grained personal access token in GitHub:

1. Choose the user or organization that owns that repository as the **resource owner**.
2. Under **Repository access**, select **Only select repositories** and choose the run-history repository.
3. Under **Repository permissions**, set **Contents** to **Read and write**. Reading is needed to display the existing run history, and writing is needed to save a run after the import CSV is downloaded.
4. Do not add any account permissions or broader repository permissions. GitHub may include read-only **Metadata** access automatically.
5. Save the generated token as `github.access_token` in `.streamlit/secrets.toml` (or in the hosted Streamlit secrets settings).

If the repository belongs to an organization, an organization administrator may need to approve the token. Give the token an appropriate expiration date and replace the configured value before it expires.

## Running locally

Install the Python packages used by the app, fill in `.streamlit/secrets.toml`, and start it from this directory:

```bash
python -m pip install -r requirements.txt
streamlit run branch_reclass_app.py
```

Raiser's Edge access uses Blackbaud's authorization flow. In the sidebar, request an authorization URL, approve access, and paste the returned authorization code into the app. Access and refresh tokens remain in the current Streamlit session rather than being written to disk.
