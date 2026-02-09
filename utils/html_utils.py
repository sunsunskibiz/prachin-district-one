import pandas as pd


def get_subdistrict_tooltip(row):
    # 1. Title: Sub-district Name
    t_val = row.get("sub_district_name", "Sub-district")
    a_val = row.get("amphoe_name", "")  # Amphoe name from extracted column

    header = f"<b>ต.{t_val}</b>"
    if a_val:
        header += f"<br/>อ.{a_val}"
    header += "<hr style='margin: 5px 0;'/>"

    # 2. Check if we have election data
    if pd.isna(row.get("ตำบล")):
        return header + "<i>No election data available</i>"

    # 3. Summary Stats
    # Users want to see: Eligible, Turnout, % Turnout
    eligible = row.get("ผู้มีสิทธิ์", 0)
    turnout = row.get("ผู้มาใช้สิทธิ์", 0)
    pct_turnout = row.get("เปอร์เซ็นต์ใช้สิทธิ์", 0)

    stats_html = f"""
    <div style='font-size: 12px; margin-bottom: 8px;'>
        <b>ผู้มีสิทธิ์:</b> {int(eligible) if pd.notna(eligible) else 0:,}<br/>
        <b>ผู้มาใช้สิทธิ์:</b> {int(turnout) if pd.notna(turnout) else 0:,} ({pct_turnout:.2f}%)
    </div>
    """

    # 4. Vote Chart (Top 5)
    vote_columns = [
        "ก้าวไกล",
        "ชาติพัฒนากล้า",
        "ชาติไทยพัฒนา",
        "ประชาชาติ",
        "ประชาธิปัตย์",
        "พลังประชารัฐ",
        "ภูมิใจไทย",
        "รวมไทยสร้างชาติ",
        "เพื่อไทย",
        "เสรีรวมไทย",
        "ไทยสร้างไทย",
    ]

    votes = {}
    for col in vote_columns:
        val = row.get(col, 0)
        if pd.notna(val):
            votes[col] = val

    max_vote = max(votes.values()) if votes and max(votes.values()) > 0 else 1
    sorted_votes = sorted(votes.items(), key=lambda item: item[1], reverse=True)[:5]

    chart_rows = []
    for col, val in sorted_votes:
        bar_width = (val / max_vote) * 100
        bar_color = "#4CAF50"
        if "เพื่อไทย" in col:
            bar_color = "#E60000"
        if "ก้าวไกล" in col:
            bar_color = "#F47920"
        if "รวมไทยสร้างชาติ" in col:
            bar_color = "#4CAF50"
        if "พลังประชารัฐ" in col:
            bar_color = "#4CAF50"
        if "ภูมิใจไทย" in col:
            bar_color = "#00366F"

        chart_rows.append(
            f"""
        <tr>
            <td style='width: 30%; font-size: 10px; padding-right:5px; white-space:nowrap;'>{col}</td>
            <td style='width: 15%; font-size: 10px; text-align:right; padding-right:5px;'>{int(val)}</td>
            <td style='width: 55%;'>
                <div style='background-color: #ddd; width: 100%; height: 8px; border-radius: 2px;'>
                    <div style='background-color: {bar_color}; width: {bar_width}%; height: 100%; border-radius: 2px;'></div>
                </div>
            </td>
        </tr>
        """
        )

    chart_table = f"<table style='width:100%; border-collapse: collapse;'>{''.join(chart_rows)}</table>"

    # 5. Visit History (Optional)
    visit_history_html = ""
    visit_records = row.get("visit_records", [])
    if visit_records:
        visit_history_html = "<div style='margin-top: 8px; border-top: 1px solid #ddd; padding-top: 5px;'>"
        visit_history_html += "<div style='font-size: 11px; font-weight: bold; color: #E65100; margin-bottom: 2px;'>ประวัติการลงพื้นที่:</div>"

        # Limit to last 5
        recent_visits = sorted(visit_records, reverse=True)[:5]
        for v in recent_visits:
            visit_history_html += (
                f"<div style='font-size: 10px; color: #555;'>• {v}</div>"
            )

        if len(visit_records) > 5:
            visit_history_html += f"<div style='font-size: 9px; color: #888; margin-top: 2px;'>...and {len(visit_records)-5} more</div>"
        visit_history_html += "</div>"

    return header + stats_html + chart_table + visit_history_html


def get_election_html(row):
    # General Info Columns
    info_columns = [
        "หน่วย",
        "ผู้มีสิทธิ์_แบ่งเขต",
        "ผู้มาใช้สิทธิ์_แบ่งเขต",
        "เปอร์เซ็นต์ใช้สิทธิ์_แบ่งเขต",
        "บัตรเสีย_แบ่งเขต",
        "ไม่เลือกผู้ใด_แบ่งเขต",
    ]

    # Vote Columns for Chart
    vote_columns = [
        "ก้าวไกล_แบ่งเขต",
        "ชาติพัฒนากล้า_แบ่งเขต",
        "ชาติไทยพัฒนา_แบ่งเขต",
        "ประชาชาติ_แบ่งเขต",
        "ประชาธิปัตย์_แบ่งเขต",
        "พลังประชารัฐ_แบ่งเขต",
        "ภูมิใจไทย_แบ่งเขต",
        "รวมไทยสร้างชาติ_แบ่งเขต",
        "เพื่อไทย_แบ่งเขต",
        "เสรีรวมไทย_แบ่งเขต",
        "ไทยสร้างไทย_แบ่งเขต",
    ]

    unit_name = row.get("ชื่อหน่วยเลือกตั้ง", "Election Unit")
    header = f"<b>{unit_name}</b><hr style='margin: 5px 0;'/>"

    # 1. Info Stats Table
    info_rows = []
    for col in info_columns:
        val = row.get(col, "-")
        info_rows.append(
            f"<tr><td style='padding-right: 10px; font-weight: bold;'>{col}:</td><td>{val}</td></tr>"
        )

    info_table = f"<table style='width:100%; border-collapse: collapse; font-size: 12px; margin-bottom: 10px;'>{''.join(info_rows)}</table>"

    # 2. Vote Chart
    # Parse votes to find max for scaling
    votes = {}
    max_vote = 1
    for col in vote_columns:
        try:
            val = float(row.get(col, 0))
        except:
            val = 0
        votes[col] = val

    if votes:
        max_vote = max(votes.values()) if max(votes.values()) > 0 else 1

    # Sort votes by value descending
    sorted_votes = sorted(votes.items(), key=lambda item: item[1], reverse=True)

    # Limit to top 5 (User Request)
    sorted_votes = sorted_votes[:5]

    chart_rows = []
    for col, val in sorted_votes:
        # Simple cleaning of column name for display (remove '_แบ่งเขต')
        display_name = col.replace("_แบ่งเขต", "")

        bar_width = (val / max_vote) * 100
        bar_color = "#4CAF50"  # Default Green
        # Optional: Custom colors for known parties
        if "เพื่อไทย" in col:
            bar_color = "#E60000"  # Red
        if "ก้าวไกล" in col:
            bar_color = "#F47920"  # Orange
        if "รวมไทยสร้างชาติ" in col:
            bar_color = "#4CAF50"  # Green (Requested)
        if "พลังประชารัฐ" in col:
            bar_color = "#4CAF50"  # Green (Requested)
        if "ภูมิใจไทย" in col:
            bar_color = "#00366F"  # Dark Blue

        chart_rows.append(
            f"""
        <tr>
            <td style='width: 30%; font-size: 10px; padding-right:5px; white-space:nowrap;'>{display_name}</td>
            <td style='width: 15%; font-size: 10px; text-align:right; padding-right:5px;'>{int(val)}</td>
            <td style='width: 55%;'>
                <div style='background-color: #ddd; width: 100%; height: 8px; border-radius: 2px;'>
                    <div style='background-color: {bar_color}; width: {bar_width}%; height: 100%; border-radius: 2px;'></div>
                </div>
            </td>
        </tr>
        """
        )

    chart_header = "<div style='font-size: 12px; font-weight: bold; margin-bottom: 2px;'>Vote Counts</div>"
    chart_table = f"<table style='width:100%; border-collapse: collapse;'>{''.join(chart_rows)}</table>"

    gmaps_link = ""
    # Google Maps Link removed as per request

    return header + info_table + chart_header + chart_table + gmaps_link


def aggregate_tooltips(series):
    # Item style: Fixed width 300px
    # Changed background to slightly darker to stand out against map, removed fixed height constraints if any
    item_style = "flex: 0 0 300px; border: 1px solid #777; padding: 8px; background: rgba(0,0,0,0.6); border-radius: 4px;"
    items = "".join([f"<div style='{item_style}'>{html}</div>" for html in series])

    # Container style: Flex wrap
    container_style = "display: flex; flex-wrap: wrap; gap: 10px; max-width: 650px;"
    return f"<div style='{container_style}'>{items}</div>"


def create_timeline_html(group):
    html = "<div style='max-height: 200px; overflow-y: auto; color: white;'>"  # color white for visibility
    html += "<b>Comments Timeline</b><hr style='margin: 4px 0;'/>"

    # Sort by timestamp (assuming formatted string YYYY-MM-DD...)
    group = group.sort_values("timestamp", ascending=False)

    for _, row in group.iterrows():
        ts = row.get("timestamp", "")
        txt = row.get("text", "")
        time_display = (
            f"<span style='font-size: 0.8em; color: #ccc;'>{ts}</span><br/>"
            if ts
            else ""
        )
        html += f"<div style='margin-bottom: 8px; border-bottom: 1px solid #ccc; padding-bottom: 4px; font-size: 12px;'>{time_display}{txt}</div>"

    html += "</div>"
    return html


def get_point_comment_tooltip(row, comments_df, df_election=None):
    """
    Generates tooltip HTML for the Point Comment tab.
    Shows Election Unit name and any contact info/comments associated with it.
    Uses lat/lon to find all units at this location.
    """
    lat = row.get("latitude")
    lon = row.get("longitude")

    # metrics
    unit_names = []

    if df_election is not None and not df_election.empty:
        # Find all units at this location
        matches = df_election[
            (df_election["latitude"] == lat) & (df_election["longitude"] == lon)
        ]
        if not matches.empty:
            unit_names = matches["ชื่อหน่วยเลือกตั้ง"].unique().tolist()

    if not unit_names:
        # Fallback if no df_election passed or no match (shouldn't happen if row comes from df_election)
        val = row.get("ชื่อหน่วยเลือกตั้ง", "Unknown Unit")
        unit_names = [val]

    # Header
    header_html = ""
    for name in unit_names:
        header_html += f"<div style='font-weight: bold; font-size: 13px; margin-bottom: 2px; color: #ff4b4b;'>{name}</div>"

    header = f"<div style='margin-bottom: 5px;'>{header_html}</div>"

    # Check for comments
    has_comments = False
    comments_html = ""

    if comments_df is not None and not comments_df.empty:
        # Filter comments for ANY of these units
        # WE match by 'target_unit' name

        # Check if target_unit column exists (it might be missing if only generic comments exist)
        if "target_unit" in comments_df.columns:
            unit_comments = comments_df[comments_df["target_unit"].isin(unit_names)]
        else:
            unit_comments = pd.DataFrame()

        if not unit_comments.empty:
            has_comments = True
            comments_html += "<div style='margin-top: 5px; border-top: 1px solid #eee; padding-top: 5px;'>"
            comments_html += "<div style='font-size: 12px; color: #aaa; margin-bottom: 3px;'>Contacts:</div>"

            for _, c_row in unit_comments.iterrows():
                name = c_row.get("contact_name", "-")
                tel = c_row.get("contact_tel", "-")
                line = c_row.get("contact_line", "-")
                note = c_row.get("text", "")
                unit = c_row.get("target_unit", "")

                # If multiple units, show which one this comment belongs to
                unit_badge = (
                    f"<div style='font-size:9px; color:#aaa;'>For: {unit}</div>"
                    if len(unit_names) > 1
                    else ""
                )

                comments_html += f"""
                <div style='background: rgba(255, 255, 255, 0.1); padding: 4px; border-radius: 4px; margin-bottom: 4px; font-size: 11px;'>
                    {unit_badge}
                    <b>{name}</b> <span style='color: #888;'>(Tel: {tel}, Line: {line})</span><br/>
                    <i style='color: #ddd;'>{note}</i>
                </div>
                """
            comments_html += "</div>"

    if not has_comments:
        comments_html = "<div style='font-size: 11px; color: #888; margin-top: 5px;'><i>Click to add contact info</i></div>"

    # Google Maps Link removed as per request
    gmaps_html = ""

    return f"<div style='min-width: 250px;'>{header}{comments_html}{gmaps_html}</div>"


def format_thai_date(date_str):
    """
    Converts YYYY-MM-DD to D MMM YYYY (Thai BE).
    Example: 2026-01-28 -> 28 ม.ค. 2569
    """
    try:
        # Simple string parsing to avoid heavy datetime deps if format is consistent
        # Assumed format: YYYY-MM-DD
        parts = date_str.split("-")
        if len(parts) != 3:
            return date_str

        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])

        thai_months = [
            "",
            "ม.ค.",
            "ก.พ.",
            "มี.ค.",
            "เม.ย.",
            "พ.ค.",
            "มิ.ย.",
            "ก.ค.",
            "ส.ค.",
            "ก.ย.",
            "ต.ค.",
            "พ.ย.",
            "ธ.ค.",
        ]

        thai_year = y + 543
        month_str = thai_months[m]

        return f"{d} {month_str} {thai_year}"
    except:
        return date_str


def get_visit_tooltip(row):
    """
    Generates tooltip HTML specifically for the Visit Record tab.
    Prioritizes Visit Data.
    """
    # 1. Header
    t_val = row.get("sub_district_name", "Sub-district")
    a_val = row.get("amphoe_name", "")

    header = f"<b>ต.{t_val}</b>"
    if a_val:
        header += f"<br/>อ.{a_val}"
    header += "<hr style='margin: 5px 0;'/>"

    # 2. Visit Data
    # Expect 'visit_records' to be a list of date strings
    visit_records = row.get("visit_records", [])
    if isinstance(visit_records, float):  # Handle NaN
        visit_records = []

    count = len(visit_records)

    html = header
    html += f"<div style='margin-bottom: 5px; color: white;'><b>Total Visits:</b> {count}</div>"
    html += "<hr style='margin: 5px 0; border-top: 1px solid rgba(255,255,255,0.3); border-bottom: 0;'/>"

    if visit_records:
        html += "<div style='font-size: 11px; max-height: 200px; overflow-y: auto;'>"
        html += "<ul style='padding-left: 15px; margin: 0; color: white;'>"

        # Sort descending
        sorted_visits = sorted(visit_records, reverse=True)

        for v in sorted_visits:
            fmt_date = format_thai_date(v)
            html += f"<li>{fmt_date}</li>"

        html += "</ul></div>"
    else:
        html += "<div style='font-size: 11px; color: #ccc; font-style: italic;'>No visits recorded</div>"

    return html
