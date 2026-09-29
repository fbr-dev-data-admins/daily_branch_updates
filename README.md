# Daily Branch Updates

## Branch assignment logic

Rules are considered in this priority order:

1. **Special event identifiers:** Serving up Hope (`Serv`) or Ardent Mills packages, or appeal identifiers ending in `GS` or `GOLF`, go to **Main**.
2. **Wyoming Gives:** Appeal identifiers ending in `WYOG` go to **Wyoming**.
3. **Gift notes:** A gift currently assigned to Main moves to **Western Slope** when its reference mentions `wslope` or `western slope`, or to **Wyoming** when it mentions `wyoming` or `wyo`.
4. **Western Slope force-in list:** A constituent on this list has a proposed branch of **Western Slope**.
5. **Online donation form:** A gift currently assigned to Main moves to **Western Slope** when the form name begins with `S`, or to **Wyoming** when it begins with `Y`.
6. **Location and monthly-donor region:** A gift currently assigned to Main can move to **Western Slope** based on one of the configured Colorado ZIP-code prefixes or a Western Slope monthly-donor region. It can move to **Wyoming** based on its state or monthly-donor region.

Only one priority category is used for each gift. When signals within that category disagree, the gift is flagged instead of being changed automatically. The app also flags repeated gift import IDs when their rows would end with different branches. Records with gift-reference text and certain Colorado records are placed in the review file even when they do not produce an automatic change.

## Output files

* **Import CSV:** Contains clear branch changes. It preserves the original branch and states which rule caused the change. For an appeal identifier ending in `WORK`, the reason also reminds staff to ensure the matching gift receives a branch update.
* **Review workbook:** Contains a `review` sheet for records that deserve attention and a `no_change` sheet for the remaining records. Every review row explains why it needs attention in the `Flag` column, including conflicts, gift-reference text, and Colorado branch checks.

## Running locally

Install the Python packages used by the app, fill in `.streamlit/secrets.toml`, and start it from this directory:

```bash
python -m pip install -r requirements.txt
streamlit run branch_reclass_app.py
```

Raiser's Edge access uses Blackbaud's authorization flow. In the sidebar, request an authorization URL, approve access, and paste the returned authorization code into the app. Access and refresh tokens remain in the current Streamlit session rather than being written to disk.
