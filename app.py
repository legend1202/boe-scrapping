from flask import Flask, request, jsonify
import pdfplumber
import re
import json
import os
import logging
from werkzeug.utils import secure_filename
from flask_cors import CORS


# Configure logging
# logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(message)s')

app = Flask(__name__)

CORS(app)  # Allow all domains or customize as needed

def extract_hours_and_dollars(tables):
    hours_by_month = {}
    dollars_by_month = {}

    for table in tables:
        if not table or not table[0]:
            continue  # Skip empty or invalid tables

        header = table[0]
        if not isinstance(header, list):  # Ensure the header is a list
            continue

        header_lower = [h.lower() if isinstance(h, str) else "" for h in header]

        # Process hours table
        if "year" in header_lower and "hours" in header_lower:
            extracted_hours = process_spread_table_dynamic_year(table, "hours")
            hours_by_month.update(extracted_hours)

        # Process dollars table
        elif "year" in header_lower and "dollars" in header_lower:
            extracted_dollars = process_spread_table_dynamic_year(table, "dollars")
            dollars_by_month.update(extracted_dollars)

        # Handle cases where headers are missing or inconsistent
        elif not hours_by_month and len(header) >= 13:
            extracted_hours = process_spread_table_dynamic_year(table, "hours")
            hours_by_month.update(extracted_hours)

        elif not dollars_by_month and len(header) >= 13:
            extracted_dollars = process_spread_table_dynamic_year(table, "dollars")
            dollars_by_month.update(extracted_dollars)

    return hours_by_month, dollars_by_month


def process_spread_table_dynamic_year(table, data_type="hours"):


    year_data = {}
    for row in table[1:]:  
        if not row or not row[0]:
            continue
        year = row[0].strip()

        if not re.match(r'^\d{4}$', year):
            # logging.debug(f"Skipping non-year row: {row}")
            continue

        try:
            months = [int(x.replace(',', '')) if x and x.replace(',', '').isdigit() else 0 for x in row[1:13]]
            year_data[year] = months
        except Exception as e:
            # logging.warning(f"Failed to process row {row}: {e}")
            continue

    return year_data


def find_task_and_next(items, name, start_date, end_date):
    
    for index, item in enumerate(items):
        if (item.get('name') == name and
            item.get('start_date') == start_date and
            item.get('end_date') == end_date):
            current_item = item
            next_item = items[index + 1] if index + 1 < len(items) else None
            return current_item, next_item
    # If not found
    return None, None


def get_tasks_by_wbs(current_task, next_task, table_positions):
    
    tasks = []

    # Sort table_positions by page_index and start_pos to ensure correct order
    table_positions_sorted = sorted(table_positions, key=lambda x: (x['page_index'], x['start_pos']))

    current_page = current_task['page_index']
    current_end_pos = current_task['start_pos']

    if next_task is not None:
        next_page = next_task['page_index']
        next_start_pos = next_task['start_pos']

        if current_page < next_page:
            for task in table_positions_sorted:
                task_page = task['page_index']
                task_start_pos = task['start_pos']

                if current_page < task_page < next_page:
                    # Tasks on pages strictly between current and next task
                    tasks.append(task)
                elif task_page == current_page:
                    # Tasks on the same page as current_task but after its end_pos
                    if task_start_pos > current_end_pos:
                        tasks.append(task)
                elif task_page == next_page:
                    # Tasks on the same page as next_task but before its start_pos
                    if task_start_pos < next_start_pos:
                        tasks.append(task)
        elif current_page == next_page:
            # Both tasks are on the same page
            for task in table_positions_sorted:
                task_page = task['page_index']
                task_start_pos = task['start_pos']

                if task_page == current_page:
                    if current_end_pos < task_start_pos < next_start_pos:
                        tasks.append(task)
        else:
            # If current_task is after next_task in page order
            print("Warning: current_task is on a higher page_index than next_task.")
    else:
        # No next_task: include tasks after current_task
        for task in table_positions_sorted:
            task_page = task['page_index']
            task_start_pos = task['start_pos']

            if task_page > current_page:
                # Tasks on pages after the current_task's page
                tasks.append(task)
            elif task_page == current_page:
                # Tasks on the same page as current_task but after its end_pos
                if task_start_pos > current_end_pos:
                    tasks.append(task)
    return tasks



def get_tables_by_task(current_task, next_task, table_positions):

    tables = []

    # Sort table_positions by page_index and start_pos to ensure correct order
    table_positions_sorted = sorted(table_positions, key=lambda x: (x['page_index'], x['start_pos']))

    current_page = current_task['page_index']
    current_end_pos = current_task['start_pos']

    if next_task is not None:
        next_page = next_task['page_index']
        next_start_pos = next_task['start_pos']

        if current_page < next_page:
            for table in table_positions_sorted:
                table_page = table['page_index']
                table_start_pos = table['start_pos']

                if current_page < table_page < next_page:
                    # Tables on pages strictly between current and next task
                    tables.append(table['data'])
                elif table_page == current_page:
                    # Tables on the same page as current_task but after its end_pos
                    if table_start_pos > current_end_pos:
                        tables.append(table['data'])
                elif table_page == next_page:
                    # Tables on the same page as next_task but before its start_pos
                    if table_start_pos < next_start_pos:
                        tables.append(table['data'])
        elif current_page == next_page:
            # Both tasks are on the same page
            for table in table_positions_sorted:
                table_page = table['page_index']
                table_start_pos = table['start_pos']

                if table_page == current_page:
                    if current_end_pos < table_start_pos < next_start_pos:
                        tables.append(table['data'])
        else:
            # If current_task is after next_task in page order
            print("Warning: current_task is on a higher page_index than next_task.")
    else:
        # No next_task: include tables after current_task
        for table in table_positions_sorted:
            table_page = table['page_index']
            table_start_pos = table['start_pos']

            if table_page > current_page:
                # Tables on pages after the current_task's page
                tables.append(table['data'])
            elif table_page == current_page:
                # Tables on the same page as current_task but after its end_pos
                if table_start_pos > current_end_pos:
                    tables.append(table['data'])

    # Output for debugging


    return tables

    

@app.route('/process-pdf', methods=['POST'])
def process_pdf():
    # Aggregate all text and tables from the PDF
    all_text = ""
    all_tables = []
    # Extract all WBS blocks
    wbs_pattern = re.compile(
        r"WBS #:\s*(.*?)\s*WBS Title:\s*(.*?)\n"
        r"CLIN #:\s*(.*?)\s*CLIN Title:\s*(.*?)\n.*?"
        r"BOE Start Date:\s*(.*?)\s*BOE End Date:\s*(.*?)\n.*?"
        r"BOE Title:\s*(.*?)\n.*?"
        r"Component:\s*(.*?)\n.*?"
        r"BOE Author:\s*(.*?)\n.*?"
        r"SOW Reference:\s*(.*?)\n.*?"
        r"BOE Description:\s*(.*?)\n",
        re.S
    )
    # Extract tasks related to the current WBS
    task_pattern = re.compile(
        r"Task\s+(\d+):\s+(.*?)\nStart Date:\s*(.*?)\s*End Date:\s*(.*?)\n",
        re.S
    )

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    file.save(filename)

    data_structure = {
        "proposalName": "",
        "WBS": []
    }
    
    try:
        with pdfplumber.open(filename) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                # Extract text from each page and concatenate
                text = page.extract_text()
                if text:
                    all_text += f"\n{text}"
                # else:
                    # logging.warning(f"No text found on page {page_num}")

                # Extract tables from each page and aggregate
                tables = page.extract_tables()
                if tables:
                    all_tables.extend(tables)

            proposal_match = re.search(r"Proposal/Program Name:\s*(.*?)\n", all_text)
            if proposal_match:
                data_structure["proposalName"] = proposal_match.group(1).strip()
                # logging.info(f"Found proposal name: {data_structure['proposalName']}")

            for wbs_match in wbs_pattern.finditer(all_text):
                current_wbs = {
                    "wbsNumber": wbs_match.group(1).strip(),
                    "wbsTitle": wbs_match.group(2).strip(),
                    "clinNumber": wbs_match.group(3).strip(),
                    "clinTitle": wbs_match.group(4).strip(),
                    "start_date": wbs_match.group(5).strip(),
                    "end_date": wbs_match.group(6).strip(),
                    "boeTitle": wbs_match.group(7).strip(),
                    "component": wbs_match.group(8).strip(),
                    "boeAuthor": wbs_match.group(9).strip(),
                    "sowReference": wbs_match.group(10).strip(),
                    "boeDescription": wbs_match.group(11).strip(),
                    "hours": 0,
                    "cost": 0,
                    "tasks": []
                }
                # logging.info(f"Detected WBS block: {current_wbs['wbsNumber']} - {current_wbs['wbsTitle']}")

                
                
                page_texts = [page.extract_text() or "" for page in pdf.pages]
                wbs_positions = []
                task_positions = []  
                table_positions = []   
                wbs_positions = []   
                for page_index, text in enumerate(page_texts):
                    wbs_matches = re.finditer(
                        r"WBS #:\s*(.*?)\s*WBS Title:\s*(.*?)\n"
                        r"CLIN #:\s*(.*?)\s*CLIN Title:\s*(.*?)\n.*?"
                        r"BOE Start Date:\s*(.*?)\s*BOE End Date:\s*(.*?)\n.*?"
                        r"BOE Title:\s*(.*?)\n.*?"
                        r"Component:\s*(.*?)\n.*?"
                        r"BOE Author:\s*(.*?)\n.*?"
                        r"SOW Reference:\s*(.*?)\n.*?"
                        r"BOE Description:\s*(.*?)\n",text        
                    )
                    for match in wbs_matches:
                        wbs_positions.append({
                            "name": match.group(2).strip(),
                            "start_date": wbs_match.group(5).strip(),
                            "end_date": wbs_match.group(6).strip(),
                            "start_pos": match.start(),
                            "end_pos": match.end(),
                            "page_index": page_index + 1
                        })   
                # output_json_path = 'wbs.json'
                # with open(output_json_path, 'w') as f:
                #     json.dump(wbs_positions, f, indent=4)

                for page_index, text in enumerate(page_texts):
                    task_matches = re.finditer(
                        r"Task\s+(\d+):\s+(.*?)\nStart Date:\s*(.*?)\s*End Date:\s*(.*?)\n", text
                    )
                    for match in task_matches:
                        task_positions.append({
                            "name": match.group(2).strip(),
                            "start_date": match.group(3).strip(),
                            "end_date": match.group(4).strip(),
                            "start_pos": match.start(),
                            "end_pos": match.end(),
                            "page_index": page_index + 1
                        })
                # output_json_path = 'tasks.json'
                # with open(output_json_path, 'w') as f:
                #     json.dump(task_positions, f, indent=4)
                for page_number, page in enumerate(pdf.pages, start=1):
                    tables = page.find_tables()
                    
                    for table in tables:
                        bbox = table.bbox  # (x0, top, x1, bottom)
                        x0, top, x1, bottom = bbox
                        table_data = table.extract()
                        table_positions.append({
                            'page_index': page_number,
                            "start_pos": top,
                            "end_pos":bottom,
                            "data": table_data
                        })
                # output_json_path = 'tables.json'
                # with open(output_json_path, 'w') as f:
                #     json.dump(table_positions, f, indent=4)
                tasks = task_pattern.findall(all_text)

                currnet_wbs_position, next_wbs_position = find_task_and_next(wbs_positions, current_wbs['wbsTitle'], current_wbs['start_date'], current_wbs['end_date'])
                tasks = get_tasks_by_wbs(currnet_wbs_position, next_wbs_position, task_positions)
                # print('===========================')
                # print(tasks)
                
                for task in tasks:
                    task_name = task['name']
                    start_date = task['start_date']
                    end_date = task['end_date']
                    # logging.info(f"Found task: {task_name}")
                    current_task, next_task = find_task_and_next(task_positions, task_name, start_date, end_date)
                    
                    # Extract hours and dollars from aggregated tables
                    tables = get_tables_by_task(current_task, next_task, table_positions)
                    hours_by_month, dollars_by_month = extract_hours_and_dollars(tables)

                    task_hours = sum(sum(months) for months in hours_by_month.values()) if hours_by_month else 0
                    task_cost = sum(sum(months) for months in dollars_by_month.values()) if dollars_by_month else 0

                    current_wbs["tasks"].append({
                        "name": task_name,
                        "start_date": start_date,
                        "end_date": end_date,
                        "spread_totals": {
                            "hours_by_month": hours_by_month,
                            "dollars_by_month": dollars_by_month
                        },
                        "description": "",
                        "hours": task_hours,
                        "cost": task_cost
                    })
                    # logging.info(f"Added task: {task_name} with {task_hours} hours and {task_cost} dollars")

                data_structure["WBS"].append(current_wbs)
                # logging.info(f"Added WBS: {current_wbs['wbsNumber']}")
            

        os.remove(filename)
        return jsonify(data_structure)

    except Exception as e:
        # logging.error(f"Error processing PDF: {e}")
        os.remove(filename)
        return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500


if __name__ == "__main__":
    app.run()
