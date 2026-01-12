import pandas as pd

def get_subdistrict_tooltip(row):
    # 1. Title: Sub-district Name
    t_val = row.get('sub_district_name', 'Sub-district')
    a_val = row.get('amphoe_name', '') # Amphoe name from extracted column
    
    header = f"<b>ต.{t_val}</b>"
    if a_val:
        header += f"<br/>อ.{a_val}"
    header += "<hr style='margin: 5px 0;'/>"

    # 2. Check if we have election data
    if pd.isna(row.get('ตำบล')):
        return header + "<i>No election data available</i>"

    # 3. Summary Stats
    # Users want to see: Eligible, Turnout, % Turnout
    eligible = row.get('ผู้มีสิทธิ์', 0)
    turnout = row.get('ผู้มาใช้สิทธิ์', 0)
    pct_turnout = row.get('เปอร์เซ็นต์ใช้สิทธิ์', 0)

    stats_html = f"""
    <div style='font-size: 12px; margin-bottom: 8px;'>
        <b>ผู้มีสิทธิ์:</b> {int(eligible) if pd.notna(eligible) else 0:,}<br/>
        <b>ผู้มาใช้สิทธิ์:</b> {int(turnout) if pd.notna(turnout) else 0:,} ({pct_turnout:.2f}%)
    </div>
    """

    # 4. Vote Chart (Top 5)
    vote_columns = [
        "ก้าวไกล", "ชาติพัฒนากล้า", "ชาติไทยพัฒนา", "ประชาชาติ", 
        "ประชาธิปัตย์", "พลังประชารัฐ", "ภูมิใจไทย", "รวมไทยสร้างชาติ", 
        "เพื่อไทย", "เสรีรวมไทย", "ไทยสร้างไทย"
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
        bar_color = '#4CAF50' 
        if 'เพื่อไทย' in col: bar_color = '#E60000'
        if 'ก้าวไกล' in col: bar_color = '#F47920'
        if 'รวมไทยสร้างชาติ' in col: bar_color = '#4CAF50'
        if 'พลังประชารัฐ' in col: bar_color = '#4CAF50'
        if 'ภูมิใจไทย' in col: bar_color = '#00366F'
        
        chart_rows.append(f"""
        <tr>
            <td style='width: 30%; font-size: 10px; padding-right:5px; white-space:nowrap;'>{col}</td>
            <td style='width: 15%; font-size: 10px; text-align:right; padding-right:5px;'>{int(val)}</td>
            <td style='width: 55%;'>
                <div style='background-color: #ddd; width: 100%; height: 8px; border-radius: 2px;'>
                    <div style='background-color: {bar_color}; width: {bar_width}%; height: 100%; border-radius: 2px;'></div>
                </div>
            </td>
        </tr>
        """)
    
    chart_table = f"<table style='width:100%; border-collapse: collapse;'>{''.join(chart_rows)}</table>"
    
    return header + stats_html + chart_table

def get_election_html(row):
    # General Info Columns
    info_columns = [
        "หน่วย", "ผู้มีสิทธิ์_แบ่งเขต", "ผู้มาใช้สิทธิ์_แบ่งเขต", "เปอร์เซ็นต์ใช้สิทธิ์_แบ่งเขต",
        "บัตรเสีย_แบ่งเขต", "ไม่เลือกผู้ใด_แบ่งเขต"
    ]

    # Vote Columns for Chart
    vote_columns = [
        "ก้าวไกล_แบ่งเขต", "ชาติพัฒนากล้า_แบ่งเขต", "ชาติไทยพัฒนา_แบ่งเขต", "ประชาชาติ_แบ่งเขต", 
        "ประชาธิปัตย์_แบ่งเขต", "พลังประชารัฐ_แบ่งเขต", "ภูมิใจไทย_แบ่งเขต", "รวมไทยสร้างชาติ_แบ่งเขต", 
        "เพื่อไทย_แบ่งเขต", "เสรีรวมไทย_แบ่งเขต", "ไทยสร้างไทย_แบ่งเขต"
    ]

    unit_name = row.get('ชื่อหน่วยเลือกตั้ง', 'Election Unit')
    header = f"<b>{unit_name}</b><hr style='margin: 5px 0;'/>"

    # 1. Info Stats Table
    info_rows = []
    for col in info_columns:
        val = row.get(col, "-")
        info_rows.append(f"<tr><td style='padding-right: 10px; font-weight: bold;'>{col}:</td><td>{val}</td></tr>")

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
        display_name = col.replace('_แบ่งเขต', '')
    
        bar_width = (val / max_vote) * 100
        bar_color = '#4CAF50' # Default Green
        # Optional: Custom colors for known parties
        if 'เพื่อไทย' in col: bar_color = '#E60000' # Red
        if 'ก้าวไกล' in col: bar_color = '#F47920' # Orange
        if 'รวมไทยสร้างชาติ' in col: bar_color = '#4CAF50' # Green (Requested)
        if 'พลังประชารัฐ' in col: bar_color = '#4CAF50' # Green (Requested)
        if 'ภูมิใจไทย' in col: bar_color = '#00366F' # Dark Blue
    
        chart_rows.append(f"""
        <tr>
            <td style='width: 30%; font-size: 10px; padding-right:5px; white-space:nowrap;'>{display_name}</td>
            <td style='width: 15%; font-size: 10px; text-align:right; padding-right:5px;'>{int(val)}</td>
            <td style='width: 55%;'>
                <div style='background-color: #ddd; width: 100%; height: 8px; border-radius: 2px;'>
                    <div style='background-color: {bar_color}; width: {bar_width}%; height: 100%; border-radius: 2px;'></div>
                </div>
            </td>
        </tr>
        """)
    
    chart_header = "<div style='font-size: 12px; font-weight: bold; margin-bottom: 2px;'>Vote Counts</div>"
    chart_table = f"<table style='width:100%; border-collapse: collapse;'>{''.join(chart_rows)}</table>"

    return header + info_table + chart_header + chart_table

def aggregate_tooltips(series):
    # Item style: Fixed width 300px
    item_style = "flex: 0 0 300px; border: 1px solid #ddd; padding: 5px; background: rgba(255,255,255,0.1); border-radius: 4px;"
    items = "".join([f"<div style='{item_style}'>{html}</div>" for html in series])
    
    # Container style: Flex wrap, set width to fit 3 items (approx 3 * 310 + gaps)
    container_style = "display: flex; flex-wrap: wrap; gap: 10px; width: fit-content; max-width: 950px;"
    return f"<div style='{container_style}'>{items}</div>"

def create_timeline_html(group):
    html = "<div style='max-height: 200px; overflow-y: auto; color: black;'>" # color black for visibility
    html += "<b>Comments Timeline</b><hr style='margin: 4px 0;'/>"
    
    # Sort by timestamp (assuming formatted string YYYY-MM-DD...)
    group = group.sort_values('timestamp', ascending=False)
    
    for _, row in group.iterrows():
        ts = row.get('timestamp', '')
        txt = row.get('text', '')
        time_display = f"<span style='font-size: 0.8em; color: #666;'>{ts}</span><br/>" if ts else ""
        html += f"<div style='margin-bottom: 8px; border-bottom: 1px solid #ccc; padding-bottom: 4px; font-size: 12px;'>{time_display}{txt}</div>"
    
    html += "</div>"
    return html
