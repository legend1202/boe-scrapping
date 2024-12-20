from flask import Flask, request, jsonify
import pdfplumber
import re
import json
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
            continue

        header = table[0]
        header_lower = [h.lower() for h in header]

        # Process hours table (either from explicit headers or default structure)
        if "year" in header_lower and "hours" in header_lower:
            # logging.debug("Found hours table, processing...")
            extracted_hours = process_spread_table_dynamic_year(table, "hours")
            hours_by_month.update(extracted_hours)

        # Process dollars table (either from explicit headers or default structure)
        elif "year" in header_lower and "dollars" in header_lower:
            # logging.debug("Found dollars table, processing...")
            extracted_dollars = process_spread_table_dynamic_year(table, "dollars")
            dollars_by_month.update(extracted_dollars)

        # Handle cases where headers are missing or inconsistent
        elif not hours_by_month and len(header) >= 13:  
            # logging.debug("Attempting to extract hours from table without standard headers...")
            extracted_hours = process_spread_table_dynamic_year(table, "hours")
            hours_by_month.update(extracted_hours)

        elif not dollars_by_month and len(header) >= 13:  
            # logging.debug("Attempting to extract dollars from table without standard headers...")
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

@app.route('/process-pdf', methods=['POST'])
def process_pdf():
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
            current_wbs = None
            current_tasks = []
            wbs_started = False

            for page_num, page in enumerate(pdf.pages, start=1):
                # logging.info(f"Processing page {page_num}")
                text = page.extract_text()

                if not text:
                    # logging.warning(f"No text found on page {page_num}")
                    continue

                if "Proposal/Program Name" in text and not data_structure["proposalName"]:
                    proposal_match = re.search(r"Proposal/Program Name:\s*(.*?)\n", text)
                    if proposal_match:
                        data_structure["proposalName"] = proposal_match.group(1).strip()
                        # logging.info(f"Found proposal name: {data_structure['proposalName']}")

                if "WBS #:" in text:
                    wbs_started = True
                    wbs_match = re.search(r"WBS #:\s*(.*?)\s*WBS Title:\s*(.*?)\n", text)
                    if wbs_match:
                        if current_wbs:
                            current_wbs["tasks"] = current_tasks
                            data_structure["WBS"].append(current_wbs)
                            # logging.info(f"Added WBS: {current_wbs['wbsNumber']}")
                            current_tasks = []
                        current_wbs = {
                            "wbsNumber": wbs_match.group(1).strip(),
                            "wbsTitle": wbs_match.group(2).strip(),
                            "clinNumber": "",
                            "clinTitle": "",
                            "start_date": "",
                            "end_date": "",
                            "boeTitle": "",
                            "component": "",
                            "boeAuthor": "",
                            "sowReference": "",
                            "boeDescription": "",
                            "hours": 0,
                            "cost": 0,
                            "tasks": []
                        }
                        # logging.info(f"Detected WBS block: {current_wbs['wbsNumber']} - {current_wbs['wbsTitle']}")

                if wbs_started and current_wbs:
                    details_match = re.search(
                        r"CLIN #:\s*(.*?)\s*CLIN Title:\s*(.*?)\n.*?BOE Start Date:\s*(.*?)\s*BOE End Date:\s*(.*?)\n.*?BOE Title:\s*(.*?)\n.*?Component:\s*(.*?)\n.*?BOE Author:\s*(.*?)\n.*?SOW Reference:\s*(.*?)\n.*?BOE Description:\s*(.*?)\n",
                        text, re.S)
                    if details_match:
                        current_wbs.update({
                            "clinNumber": details_match.group(1).strip(),
                            "clinTitle": details_match.group(2).strip(),
                            "start_date": details_match.group(3).strip(),
                            "end_date": details_match.group(4).strip(),
                            "boeTitle": details_match.group(5).strip(),
                            "component": details_match.group(6).strip(),
                            "boeAuthor": details_match.group(7).strip(),
                            "sowReference": details_match.group(8).strip(),
                            "boeDescription": details_match.group(9).strip()
                        })
                        # logging.info(f"Extracted WBS details for {current_wbs['wbsNumber']}")

                task_matches = re.finditer(r"Task\s+(\d+):\s+(.*?)\nStart Date:\s*(.*?)\s*End Date:\s*(.*?)\n", text)
                for match in task_matches:
                    task_name = match.group(2).strip()
                    start_date = match.group(3).strip()
                    end_date = match.group(4).strip()
                    # logging.info(f"Found task: {task_name}")

                    hours_by_month = {}
                    dollars_by_month = {}
                    tables = page.extract_tables()

                    hours_by_month, dollars_by_month = extract_hours_and_dollars(tables)

                    task_hours = sum(sum(months) for months in hours_by_month.values()) if hours_by_month else 0
                    task_cost = sum(sum(months) for months in dollars_by_month.values()) if dollars_by_month else 0

                    current_tasks.append({
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

            if current_wbs:
                current_wbs["tasks"] = current_tasks
                data_structure["WBS"].append(current_wbs)
                # logging.info(f"Added final WBS: {current_wbs['wbsNumber']}")

        return jsonify(data_structure)

    except Exception as e:
        # logging.error(f"Error processing PDF: {e}")
        return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500


if __name__ == "__main__":
    app.run()
