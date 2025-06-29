
import dash
import dash_auth
from dash import dcc, html, Input, Output, State, dash_table
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import sqlite3
import hashlib
import Dashauth
import qrcode
import io
import os
import base64
from datetime import datetime, timedelta
import json
import random
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from PIL import Image as PILImage, ImageDraw, ImageFont

# --- App Initialization with Bootstrap Theme and Font Awesome Icons ---
FA = "https://use.fontawesome.com/releases/v5.15.4/css/all.css"
app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.FLATLY, FA])

app.index_string = '''<!DOCTYPE html>
<html>
<head>
<title>FTL</title>
<link rel="manifest" href="./assets/manifest.json" />
{%metas%}
{%favicon%}
{%css%}
</head>
<script type="module">
   import 'https://cdn.jsdelivr.net/npm/@pwabuilder/pwaupdate';
   const el = document.createElement('pwa-update');
   document.body.appendChild(el);
</script>
<body>
<script>
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', ()=> {
      navigator
      .serviceWorker
      .register('./assets/pwabuilder-sw.js')
      .then(()=>console.log("Ready."))
      .catch(()=>console.log("Err..."));
    });
  }
</script>
{%app_entry%}
<footer>
{%config%}
{%scripts%}
{%renderer%}
</footer>
</body>
</html>
'''

app.title = "Fuel Transport Ledger - South Sudan"
DB_FILE = 'fuel_transport_ledger_v7.6_final.db'
LOGO_FILE = "logo.PNG"

server = app.server


auth = dash_auth.BasicAuth(
    app,
    Dashauth.VALID_USERNAME_PASSWORD_PAIRS
)

# --- List of African Countries for Dropdown ---
AFRICAN_COUNTRIES = [
    'Algeria', 'Angola', 'Benin', 'Botswana', 'Burkina Faso', 'Burundi', 'Cabo Verde',
    'Cameroon', 'Central African Republic', 'Chad', 'Comoros', 'Congo (Congo-Brazzaville)',
    'Congo (DRC)', 'Cote d\'Ivoire', 'Djibouti', 'Egypt', 'Equatorial Guinea', 'Eritrea',
    'Eswatini', 'Ethiopia', 'Gabon', 'Gambia', 'Ghana', 'Guinea', 'Guinea-Bissau',
    'Kenya', 'Lesotho', 'Liberia', 'Libya', 'Madagascar', 'Malawi', 'Mali', 'Mauritania',
    'Mauritius', 'Morocco', 'Mozambique', 'Namibia', 'Niger', 'Nigeria', 'Rwanda',
    'Sao Tome and Principe', 'Senegal', 'Seychelles', 'Sierra Leone', 'Somalia',
    'South Africa', 'South Sudan', 'Sudan', 'Tanzania', 'Togo', 'Tunisia', 'Uganda',
    'Zambia', 'Zimbabwe'
]


# --- Database Schema Setup ---
def init_database():
    """Initializes the database and tables, updating the schema if necessary."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Create tables if they don't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY, plate_number TEXT UNIQUE, driver_name TEXT, driver_id TEXT,
            driver_nationality TEXT, driver_passport_image_path TEXT, company_name TEXT,
            company_till_number TEXT, invoice_number TEXT, amount_paid REAL, origin TEXT,
            destination TEXT, fuel_volume REAL, created_at TIMESTAMP, status TEXT, unique_hash TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checkpoints (
            id INTEGER PRIMARY KEY, vehicle_id INTEGER, checkpoint_name TEXT, officer_name TEXT,
            timestamp TIMESTAMP, fuel_volume_check REAL, notes TEXT,
            previous_hash TEXT, signature_hash TEXT,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles (id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS officers (
            id INTEGER PRIMARY KEY, name TEXT, badge_number TEXT, checkpoint_location TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_validation (
            invoice_number TEXT PRIMARY KEY, amount_paid REAL
        )
    ''')

    # Schema update logic to handle old databases.
    # This ensures the `image_path` column exists in the `checkpoints` table.
    cursor.execute("PRAGMA table_info(checkpoints)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'image_path' not in columns:
        print("INFO: 'image_path' column not found in 'checkpoints' table. Attempting to update schema...")
        if 'image_data' in columns:
            print("INFO: Found old 'image_data' column. Renaming to 'image_path'.")
            cursor.execute("ALTER TABLE checkpoints RENAME COLUMN image_data TO image_path")
        else:
            print("INFO: Adding 'image_path' column to 'checkpoints' table.")
            cursor.execute("ALTER TABLE checkpoints ADD COLUMN image_path TEXT")

    conn.commit()
    conn.close()


# --- Comprehensive Database Seeder with Scenarios ---
def seed_database():
    """Populates all database tables with specific scenarios for testing."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if cursor.execute("SELECT COUNT(*) FROM officers").fetchone()[0] > 0:
        conn.close()
        return

    print("INFO: Seeding database with test data...")
    locations = ['Juba', 'Wau', 'Malakal', 'Bor', 'Torit', 'Yei', 'Aweil', 'Bentiu', 'Rumbek', 'Yambio']
    officer_names = [
        'John Makur', 'Mary Adut', 'Peter Deng', 'Sarah Nyong', 'James Lado', 'Achan Garang',
        'Mawien Dut', 'Nadia Kiden', 'Simon Tembura', 'Grace Akol', 'David Kual', 'Rebecca Yar',
        'Joseph Mading', 'Hawa Juma', 'Emmanuel Taban', 'Isaac Kenyi', 'Joyce Poni'
    ]
    officers_to_add = []
    for i, name in enumerate(officer_names):
        officers_to_add.append((name, f"CP{i + 1:03d}", random.choice(locations)))
    cursor.executemany('INSERT INTO officers (name, badge_number, checkpoint_location) VALUES (?, ?, ?)',
                       officers_to_add)

    simulated_payments = []
    for i in range(30):
        simulated_payments.append((f"INV{random.randint(10000, 99999)}", round(random.uniform(5000.0, 50000.0), 2)))
    cursor.executemany('INSERT OR IGNORE INTO payment_validation (invoice_number, amount_paid) VALUES (?, ?)',
                       simulated_payments)

    payment_records = cursor.execute("SELECT invoice_number, amount_paid FROM payment_validation").fetchall()
    random.shuffle(payment_records)

    sample_drivers = ['Ali Mohammed', 'Grace Nakato', 'Samuel Okech', 'Fatima Yusuf', 'Daniel Wani']
    sample_companies = ['Nile Petroleum', 'Savannah Fuels Ltd', 'Equator Energy', 'Sudan Oil Co', 'Juba Logistics']

    passports_dir = os.path.join('assets', 'passports')
    if not os.path.exists(passports_dir): os.makedirs(passports_dir)
    placeholder_passport = os.path.join(passports_dir, 'placeholder.png')
    if not os.path.exists(placeholder_passport):
        img = PILImage.new('RGB', (100, 120), color='grey')
        d = ImageDraw.Draw(img);
        d.text((10, 50), "Placeholder", fill='white');
        img.save(placeholder_passport)

    evidence_dir = os.path.join('assets', 'checkpoint_evidence')
    if not os.path.exists(evidence_dir): os.makedirs(evidence_dir)
    placeholder_evidence_path = os.path.join(evidence_dir, 'placeholder_evidence.PNG')
    if not os.path.exists(placeholder_evidence_path):
        img = PILImage.new('RGB', (400, 100), color=colors.lightgrey.hexval)
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except IOError:
            font = ImageFont.load_default()
        d.text((10, 10), "SAMPLE EVIDENCE PHOTO\nMeter Reading", fill='black', font=font)
        img.save(placeholder_evidence_path)

    vehicle_data_list = []
    scenarios = ['fuel_increase'] * 2 + ['suspicious_decrease'] * 2 + ['critical_decrease'] * 1
    total_vehicles = 25

    for i in range(total_vehicles):
        scenario_type = 'normal'
        status = 'in_transit' if i < 15 and i % 2 == 0 else 'completed'
        created = datetime.now() - timedelta(days=random.randint(0, 5 if i < 15 else 30), hours=random.randint(1, 23))

        plate = f"SSD-{random.randint(1000, 9999)}-{i}"
        driver = random.choice(sample_drivers)
        inv_num, amt_paid = payment_records.pop()
        route = random.sample(locations, 2)

        vehicle_data_list.append({
            "plate_number": plate, "driver_name": driver, "driver_id": f"NAT{random.randint(100000, 999999)}",
            "driver_nationality": random.choice(AFRICAN_COUNTRIES), "driver_passport_image_path": placeholder_passport,
            "company_name": random.choice(sample_companies),
            "company_till_number": f"{random.randint(100, 999)}-{random.randint(100, 999)}",
            "invoice_number": inv_num, "amount_paid": amt_paid, "origin": route[0], "destination": route[1],
            "fuel_volume": float(random.choice([20000, 35000])), "created_at": created, "status": status,
            "unique_hash": generate_unique_hash(f"{plate}{driver}{created}"), "scenario": scenario_type
        })

    vehicles_to_insert = [{k: v for k, v in d.items() if k != 'scenario'} for d in vehicle_data_list]
    cursor.executemany('''INSERT INTO vehicles (plate_number, driver_name, driver_id, driver_nationality,
                         driver_passport_image_path, company_name, company_till_number, invoice_number,
                         amount_paid, origin, destination, fuel_volume, created_at, status, unique_hash)
                         VALUES (:plate_number, :driver_name, :driver_id, :driver_nationality, :driver_passport_image_path,
                         :company_name, :company_till_number, :invoice_number, :amount_paid, :origin, :destination,
                         :fuel_volume, :created_at, :status, :unique_hash)''', vehicles_to_insert)

    vehicle_db_data = cursor.execute("SELECT id, plate_number FROM vehicles").fetchall()
    vehicle_id_map = {plate: v_id for v_id, plate in vehicle_db_data}
    checkpoints_to_add = []

    for v_data in vehicle_data_list:
        v_id = vehicle_id_map.get(v_data['plate_number'])
        if not v_id: continue

        last_hash, last_fuel, last_time = v_data['unique_hash'], v_data['fuel_volume'], v_data['created_at']
        num_stops = random.randint(3, 5) if v_data['status'] == 'completed' else random.randint(1, 2)
        anomaly_stop = random.randint(1, num_stops - 1) if num_stops > 1 else 0

        for i in range(num_stops):
            last_time += timedelta(hours=random.randint(5, 12))
            loc = v_data['destination'] if i == num_stops - 1 and v_data['status'] == 'completed' else random.choice(
                locations)
            officers_at_loc = [row[0] for row in cursor.execute("SELECT name FROM officers WHERE checkpoint_location=?",
                                                                (loc,)).fetchall()]
            officer = random.choice(officers_at_loc) if officers_at_loc else "Default Officer"
            notes = ''

            image_path_to_add = placeholder_evidence_path if v_data['status'] == 'completed' else None

            if i == anomaly_stop and v_data['scenario'] != 'normal':
                if v_data['scenario'] == 'fuel_increase':
                    last_fuel += random.uniform(51, 200); notes = "Anomaly detected: Fuel volume increased."
                elif v_data['scenario'] == 'suspicious_decrease':
                    last_fuel -= random.uniform(251, 999); notes = "Suspicious fuel loss detected."
                elif v_data['scenario'] == 'critical_decrease':
                    last_fuel -= random.uniform(1001, 2500); notes = "CRITICAL fuel loss detected."
            else:
                last_fuel -= random.uniform(50, 250)

            fuel_check = round(max(0, last_fuel), 2)
            s_hash = generate_unique_hash(
                f"{v_id}{loc}{officer}{last_time}{fuel_check}{notes or ''}{image_path_to_add or ''}{last_hash}")
            checkpoints_to_add.append(
                (v_id, loc, officer, last_time, fuel_check, notes, image_path_to_add, last_hash, s_hash))
            last_hash = s_hash
            if fuel_check <= 0: break

    cursor.executemany('''INSERT INTO checkpoints (vehicle_id, checkpoint_name, officer_name, timestamp,
                         fuel_volume_check, notes, image_path, previous_hash, signature_hash)
                         VALUES (?,?,?,?,?,?,?,?,?)''', checkpoints_to_add)

    conn.commit()
    conn.close()
    print("INFO: Database seeding process completed.")


# --- UTILITY AND PDF FUNCTIONS ---
def generate_unique_hash(data):
    """Generates a SHA-256 hash for given data."""
    return hashlib.sha256(str(data).encode()).hexdigest()


def generate_qr_code_b64(data):
    """Generates a QR code and returns it as a Base64 encoded string."""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data);
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO();
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def get_checkpoint_locations():
    """Fetches unique checkpoint locations from the database for dropdowns."""
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql_query('SELECT DISTINCT checkpoint_location FROM officers', conn)[
            'checkpoint_location'].tolist()


def get_officers_by_checkpoint(checkpoint):
    """Fetches officers based on their assigned checkpoint location."""
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql_query('SELECT name, badge_number FROM officers WHERE checkpoint_location = ?', conn,
                                 params=[checkpoint])


class CHRL(Flowable):
    """A custom ReportLab flowable for a horizontal line."""

    def __init__(self, width, thickness=1, color=colors.black):
        Flowable.__init__(self)
        self.width = width
        self.thickness = thickness
        self.color = color

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.width, 0)


def create_journey_pdf(journey_id):
    """Generates a comprehensive PDF report for a given journey ID."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            vehicle = pd.read_sql_query("SELECT * FROM vehicles WHERE id = ?", conn, params=[journey_id]).iloc[0]
            checkpoints = pd.read_sql_query("SELECT * FROM checkpoints WHERE vehicle_id = ? ORDER BY timestamp", conn,
                                            params=[journey_id])

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                                topMargin=0.5 * inch, bottomMargin=0.5 * inch)

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='ReportTitle', fontSize=22, fontName='Helvetica-Bold', alignment=TA_RIGHT,
                                  textColor=colors.HexColor("#0D47A1")))
        styles.add(ParagraphStyle(name='ReportSubtitle', fontSize=11, fontName='Helvetica-Oblique', alignment=TA_RIGHT,
                                  textColor=colors.grey))
        styles.add(
            ParagraphStyle(name='SectionHeader', fontSize=16, fontName='Helvetica-Bold', spaceBefore=24, spaceAfter=12,
                           textColor=colors.HexColor("#0D47A1")))
        styles.add(ParagraphStyle(name='DetailKey', fontSize=9, fontName='Helvetica-Bold'))
        styles.add(ParagraphStyle(name='DetailValue', fontSize=11, fontName='Helvetica'))
        styles.add(ParagraphStyle(name='NotesStyle', fontSize=9, fontName='Helvetica', leading=12))
        styles.add(ParagraphStyle(name='FooterText', fontSize=8, fontName='Helvetica', alignment=TA_CENTER,
                                  textColor=colors.grey))
        styles.add(ParagraphStyle(name='RightAlign', alignment=TA_RIGHT))
        # Style for the hash values to make them smaller
        styles.add(ParagraphStyle(name='HashStyle', fontSize=7, fontName='Courier', leading=8))

        story = []

        logo_path = os.path.join('assets', LOGO_FILE)
        logo_img = Image(logo_path, width=1.5 * inch, height=0.75 * inch, kind='proportional') if os.path.exists(
            logo_path) else Paragraph("[Logo]", styles['Normal'])
        header_data = [[logo_img, [Paragraph("Official Journey Report", styles['ReportTitle']), Spacer(1, 12),
                                   Paragraph(f"Vehicle: <b>{vehicle['plate_number']}</b>", styles['ReportSubtitle'])]]]
        header_table = Table(header_data, colWidths=[2.0 * inch, 5.5 * inch])
        header_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'BOTTOM')]))
        story.append(header_table)
        story.append(CHRL(7.5 * inch, thickness=2, color=colors.HexColor("#0D47A1")))
        story.append(Spacer(1, 0.3 * inch))

        passport_image = Paragraph("[No Image]", styles['Normal'])
        if vehicle['driver_passport_image_path'] and os.path.exists(vehicle['driver_passport_image_path']):
            try:
                passport_image = Image(vehicle['driver_passport_image_path'], width=1.0 * inch, height=1.2 * inch)
            except Exception:
                passport_image = Paragraph("[Error]", styles['Normal'])

        final_hash = checkpoints['signature_hash'].iloc[-1] if not checkpoints.empty else vehicle['unique_hash']
        qr_data = json.dumps({'plate': vehicle['plate_number'], 'final_hash': final_hash})
        qr_code_image = Image(io.BytesIO(base64.b64decode(generate_qr_code_b64(qr_data))), width=1.2 * inch,
                              height=1.2 * inch)

        details_data = [
            [Paragraph("<b>Company</b>", styles['DetailKey']),
             Paragraph(vehicle['company_name'], styles['DetailValue']), Paragraph("<b>Driver</b>", styles['DetailKey']),
             Paragraph(f"{vehicle['driver_name']} ({vehicle['driver_nationality']})", styles['DetailValue']),
             passport_image],
            [Paragraph("<b>Route</b>", styles['DetailKey']),
             Paragraph(f"{vehicle['origin']} ➔ {vehicle['destination']}", styles['DetailValue']),
             Paragraph("<b>Dispatched</b>", styles['DetailKey']),
             Paragraph(f"{pd.to_datetime(vehicle['created_at']).strftime('%Y-%m-%d %H:%M')}", styles['DetailValue']),
             ''],
            [Paragraph("<b>Invoice No.</b>", styles['DetailKey']),
             Paragraph(vehicle['invoice_number'], styles['DetailValue']),
             Paragraph("<b>Amount Paid</b>", styles['DetailKey']),
             Paragraph(f"${vehicle['amount_paid']:,.2f}", styles['DetailValue']), qr_code_image],
            [Paragraph("<b>Initial Fuel</b>", styles['DetailKey']),
             Paragraph(f"{vehicle['fuel_volume']:,.0f} Liters", styles['DetailValue']), '', '', '']
        ]
        details_table = Table(details_data, colWidths=[1.0 * inch, 2.0 * inch, 1.0 * inch, 2.0 * inch, 1.5 * inch])
        details_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-2, -1), 1, colors.lightgrey),
            ('SPAN', (4, 0), (4, 1)), ('ALIGN', (4, 0), (4, 1), 'CENTER'),
            ('SPAN', (4, 2), (4, 3)), ('ALIGN', (4, 2), (4, 3), 'CENTER'),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#E3F2FD")),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor("#E3F2FD")),
        ]))
        story.append(details_table)
        story.append(Spacer(1, 0.3 * inch))

        is_chain_valid = all(
            row['previous_hash'] == (checkpoints['signature_hash'].iloc[i - 1] if i > 0 else vehicle['unique_hash']) for
            i, row in checkpoints.iterrows())
        integrity_p = Paragraph(
            f'✔ <font color="#2E7D32"><b>Chain Verified:</b> The log is complete and untampered.</font>' if is_chain_valid else f'❌ <font color="#C62828"><b>Chain Broken:</b> The log integrity is compromised!</font>',
            styles['Normal'])
        story.append(integrity_p)
        story.append(Spacer(1, 0.2 * inch))

        # Add Genesis Hash
        story.append(Paragraph(
            f"<b>Genesis Hash:</b> <font size=7 face=Courier>{vehicle['unique_hash'][:12]}...{vehicle['unique_hash'][-12:]}</font>",
            styles['Normal']))
        story.append(Spacer(1, 0.2 * inch))

        story.append(Paragraph("Checkpoint Ledger", styles['SectionHeader']))
        story.append(CHRL(7.5 * inch, color=colors.HexColor("#B0BEC5")))

        last_fuel = vehicle['fuel_volume']
        for i, row in checkpoints.iterrows():
            discrepancy = last_fuel - row['fuel_volume_check']
            last_fuel = row['fuel_volume_check']

            if discrepancy < -50:
                disc_color, disc_text = colors.red, "<b>ANOMALY (INCREASE)</b>"
            elif discrepancy > 1000:
                disc_color, disc_text = colors.darkred, "<b>CRITICAL LOSS</b>"
            elif discrepancy > 250:
                disc_color, disc_text = colors.orange, "<b>SUSPICIOUS LOSS</b>"
            else:
                disc_color, disc_text = colors.darkgreen, "Normal Consumption"

            cp_header_data = [[Paragraph(f"<b>Checkpoint {i + 1}:</b> {row['checkpoint_name']}", styles['Normal']),
                               Paragraph(
                                   f"<b>Timestamp:</b> {pd.to_datetime(row['timestamp']).strftime('%Y-%m-%d %H:%M')}",
                                   styles['RightAlign'])]]
            story.append(Table(cp_header_data, colWidths=[3.75 * inch, 3.75 * inch],
                               style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#E3F2FD"))])))

            cp_details_data = [
                [Paragraph("<b>Officer:</b>", styles['DetailKey']),
                 Paragraph(row['officer_name'], styles['DetailValue'])],
                [Paragraph("<b>Fuel Check:</b>", styles['DetailKey']),
                 Paragraph(f"{row['fuel_volume_check']:,.0f} L", styles['DetailValue'])],
                [Paragraph("<b>Discrepancy:</b>", styles['DetailKey']),
                 Paragraph(f"<font color='{disc_color.hexval()}'>{disc_text}: {discrepancy:,.1f} L</font>",
                           styles['DetailValue'])]
            ]

            if row['notes']:
                cp_details_data.append(
                    [Paragraph("<b>Notes:</b>", styles['DetailKey']), Paragraph(row['notes'], styles['NotesStyle'])])

            # **UPDATED**: Add truncated hashes to the report.
            if 'previous_hash' in row and row['previous_hash']:
                prev_hash = row['previous_hash']
                prev_hash_display = f"{prev_hash[:12]}...{prev_hash[-12:]}"
                cp_details_data.append([Paragraph("<b>Prev Hash:</b>", styles['DetailKey']),
                                        Paragraph(prev_hash_display, styles['HashStyle'])])

            if 'signature_hash' in row and row['signature_hash']:
                sig_hash = row['signature_hash']
                sig_hash_display = f"{sig_hash[:12]}...{sig_hash[-12:]}"
                cp_details_data.append([Paragraph("<b>Checkpoint Hash:</b>", styles['DetailKey']),
                                        Paragraph(sig_hash_display, styles['HashStyle'])])

            if 'image_path' in row and row['image_path'] and os.path.exists(row['image_path']):
                try:
                    pil_img = PILImage.open(row['image_path'])
                    pil_img.verify()  # Verify image integrity
                    pil_img.close()

                    # Reopen for ReportLab
                    pil_img_for_reportlab = PILImage.open(row['image_path'])
                    pil_img_for_reportlab.load()
                    img_reader = ImageReader(pil_img_for_reportlab)

                    img = Image(img_reader, width=3 * inch, kind='proportional')
                    img.hAlign = 'LEFT'
                    cp_details_data.append([Paragraph("<b>Evidence:</b>", styles['DetailKey']), img])
                except Exception as e:
                    print(f"PDF Image Error: Could not load or process image from path {row['image_path']}. Error: {e}")
                    cp_details_data.append([Paragraph("<b>Evidence:</b>", styles['DetailKey']),
                                            Paragraph("[Image File Error]", styles['NotesStyle'])])

            cp_details_table = Table(cp_details_data, colWidths=[1.2 * inch, 6.3 * inch])
            cp_details_table.setStyle(
                TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey)]))
            story.append(cp_details_table)
            story.append(Spacer(1, 0.3 * inch))

        def footer(canvas, doc):
            canvas.saveState()
            footer_text = "Defyhatenow EA Office | Juba, Hai-Malakal, Nimule Street | Tel: +211 922 007 505"
            page_num_text = f"Page {doc.page}"
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.grey)
            canvas.drawCentredString(letter[0] / 2.0, 0.3 * inch, footer_text)
            canvas.drawRightString(letter[0] - 0.5 * inch, 0.3 * inch, page_num_text)
            canvas.restoreState()

        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        print(f"CRITICAL ERROR in create_journey_pdf: {e}")
        return None


# --- APP LAYOUT AND STYLING ---
def create_navbar():
    """Creates the main navigation bar for the application."""
    logo_path = os.path.join('assets', LOGO_FILE)
    logo_display = html.Img(src=app.get_asset_url(LOGO_FILE),
                            style={'height': '35px', 'margin-right': '15px'}) if os.path.exists(logo_path) else html.I(
        className="fas fa-truck-moving me-2")
    return dbc.NavbarSimple(
        children=[
            dbc.NavItem(dbc.NavLink("Dashboard", href="/")),
            dbc.NavItem(dbc.NavLink("Register Vehicle", href="/register")),
            dbc.NavItem(dbc.NavLink("Checkpoint Login", href="/checkpoint")),
            dbc.NavItem(dbc.NavLink("Route Monitor", href="/monitor")),
            dbc.NavItem(dbc.NavLink("Download Reports", href="/receipt")),
        ], brand=html.Span([logo_display, "Fuel Transport Ledger"]), brand_href="/", color="primary", dark=True,
        className="mb-4",
    )


app.layout = html.Div([
    dcc.Store(id='checkpoint-data-store'),
    dcc.Location(id='url', refresh=False),
    create_navbar(),
    dbc.Container(id='page-content', fluid=True)
])


def create_kpi_card(title, value_id, icon, color):
    """Helper function to create a KPI card for the dashboard."""
    return dbc.Card(dbc.CardBody([
        html.H4(html.I(className=f"{icon} me-2"), className=f"text-{color}"),
        html.H3(id=value_id),
        html.P(title, className="card-title"),
    ]))


# --- PAGE LAYOUTS ---
def dashboard_layout():
    return html.Div([
        dbc.Row(dbc.Col(
            html.H2(html.Span([html.I(className="fas fa-tachometer-alt me-2"), " Live Operations Dashboard"])))),
        html.Hr(),
        dbc.Row([
            dbc.Col(create_kpi_card("Active Transports", "active-transports", "fas fa-shipping-fast", "primary"), md=3),
            dbc.Col(create_kpi_card("Completed Today", "completed-today", "fas fa-check-circle", "success"), md=3),
            dbc.Col(create_kpi_card("Overdue", "overdue-transports", "fas fa-exclamation-triangle", "danger"), md=3),
            dbc.Col(create_kpi_card("Total Fuel In-Transit (L)", "total-fuel", "fas fa-gas-pump", "warning"), md=3),
        ], className="mb-4"),
        dbc.Row([
            dbc.Col(dbc.Card(dcc.Graph(id='transport-status-chart')), md=6),
            dbc.Col(dbc.Card(dcc.Graph(id='checkpoint-activity-chart')), md=6),
        ], className="mb-4"),
        dbc.Card(dbc.CardBody([
            html.H4(html.Span([html.I(className="fas fa-history me-2"), " Recent Journeys"])),
            html.Div(id='active-transports-table')
        ])),
        dcc.Interval(id='interval-component', interval=30 * 1000, n_intervals=0)
    ])


def register_layout():
    return dbc.Row(dbc.Col(dbc.Card(dbc.CardBody([
        html.H3(html.Span([html.I(className="fas fa-plus-circle me-2"), " Register New Fuel Transport"])), html.Hr(),
        dbc.Form([
            dbc.Row([
                dbc.Col(html.Div(
                    [dbc.Label("Vehicle Plate Number"), dbc.Input(id='plate-number', placeholder='e.g., SSD-1234')],
                    className="mb-3"), md=6),
                dbc.Col(html.Div([dbc.Label("Driver Name"), dbc.Input(id='driver-name', placeholder='Full name')],
                                 className="mb-3"), md=6),
            ]),
            dbc.Row([
                dbc.Col(
                    html.Div([dbc.Label("Driver ID"), dbc.Input(id='driver-id', placeholder='National ID or License')],
                             className="mb-3"), md=6),
                dbc.Col(html.Div([dbc.Label("Driver Nationality"),
                                  dcc.Dropdown(id='driver-nationality', options=AFRICAN_COUNTRIES,
                                               placeholder="Select country")], className="mb-3"), md=6),
            ]),
            html.Div([
                dbc.Label("Upload Driver Passport Image", className="fw-bold"),
                dcc.Upload(id='upload-passport-image', children=html.Div(['Drag and Drop or ', html.A('Select Image')]),
                           style={'width': '100%', 'height': '60px', 'lineHeight': '60px', 'borderWidth': '1px',
                                  'borderStyle': 'dashed', 'borderRadius': '5px', 'textAlign': 'center'},
                           multiple=False),
                html.Div(id='output-passport-upload', className='text-center mt-2')
            ], className="mb-3 border rounded p-3"),
            html.Hr(),
            html.H4("Company & Payment Details", className="mt-4 mb-3"),
            html.H5("CapitalPay Invoice Verification", className="mt-4 mb-3 text-muted"),
            dbc.Row([
                dbc.Col(html.Div(
                    [dbc.Label("Company Name"), dbc.Input(id='company-name', placeholder='e.g., Africa Fuel Corp')],
                    className="mb-3"), md=6),
                dbc.Col(html.Div(
                    [dbc.Label("Unique Till Number"), dbc.Input(id='company-till', placeholder='e.g., 987654')],
                    className="mb-3"), md=6),
            ]),
            dbc.Row([
                dbc.Col(html.Div([dbc.Label("Invoice Number"), dbc.InputGroup(
                    [dbc.Input(id='invoice-number', placeholder='e.g., INV12345'),
                     dbc.Button(html.I(className="fas fa-info-circle"), id="invoice-help-target", color="info",
                                n_clicks=0)])], className="mb-3"), md=6),
                dbc.Col(html.Div([dbc.Label("Amount Paid"),
                                  dbc.Input(id='amount-paid', type='number', placeholder='e.g., 15000.50')],
                                 className="mb-3"), md=6),
            ]),
            dbc.Popover([dbc.PopoverHeader("Valid Test Invoices"),
                         dbc.PopoverBody(dcc.Loading(html.Div(id="invoice-list-container")))], id="invoice-popover",
                        target="invoice-help-target", trigger="click", placement="right"),
            html.Hr(),
            html.H4("Journey Details", className="mt-4 mb-3"),
            dbc.Row([
                dbc.Col(html.Div([dbc.Label("Fuel Volume (Liters)"),
                                  dbc.Input(id='fuel-volume', type='number', placeholder='e.g., 35000')],
                                 className="mb-3"), md=12),
            ]),
            dbc.Row([
                dbc.Col(html.Div(
                    [dbc.Label("Departure Location"), dcc.Dropdown(id='origin', options=get_checkpoint_locations())],
                    className="mb-3"), md=6),
                dbc.Col(html.Div(
                    [dbc.Label("Destination"), dcc.Dropdown(id='destination', options=get_checkpoint_locations())],
                    className="mb-3"), md=6),
            ]),
            dbc.Button(html.Span([html.I(className="fas fa-paper-plane me-2"), " Register Vehicle"]), id='register-btn',
                       color='primary', className='mt-3 w-100'),
            html.Div(id='register-output', className='mt-4')
        ])
    ])), lg=8, md=10), justify="center")


def checkpoint_layout():
    return dbc.Row(dbc.Col(dbc.Card(dbc.CardBody([
        html.H3(html.Span([html.I(className="fas fa-map-marker-alt me-2"), " Checkpoint Login & Ledger Entry"])),
        html.Hr(),
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle(
                html.Span([html.I(className="fas fa-exclamation-triangle text-warning me-2"), "Confirm Reading"]))),
            dbc.ModalBody(id='confirm-modal-body'),
            dbc.ModalFooter([
                dbc.Button("Cancel", id="cancel-confirm-btn", color="secondary"),
                dbc.Button("Submit Anyway", id="submit-confirm-btn", color="danger"),
            ]),
        ], id="confirmation-modal", is_open=False),
        dbc.Form([
            html.Div([dbc.Label("Vehicle Plate Number"),
                      dbc.Input(id='cp-plate-number', placeholder='Enter plate number to fetch last reading',
                                persistence=True, persistence_type='session')], className="mb-3", ),
            html.Div(id='last-reading-info', className="mb-3 p-3 border rounded bg-light"),
            dbc.Row([
                dbc.Col(html.Div([dbc.Label("Checkpoint Location"),
                                  dcc.Dropdown(id='checkpoint-location', options=get_checkpoint_locations())],
                                 className="mb-3"), md=6),
                dbc.Col(html.Div([dbc.Label("Officer on Duty"), dcc.Dropdown(id='officer-select')], className="mb-3"),
                        md=6),
            ]),
            html.Div([dbc.Label("Fuel Volume Check (Liters)"),
                      dbc.Input(id='fuel-check', type='number', placeholder='Current measured fuel volume')],
                     className="mb-3"),
            html.Div([
                dbc.Label("Upload Image Evidence (Optional)", className="fw-bold"),
                dcc.Upload(id='upload-checkpoint-image',
                           children=html.Div(['Drag and Drop or ', html.A('Select Image')]),
                           style={'width': '100%', 'height': '60px', 'lineHeight': '60px', 'borderWidth': '1px',
                                  'borderStyle': 'dashed', 'borderRadius': '5px', 'textAlign': 'center'}, ),
                html.Div(id='output-checkpoint-image-upload', className='text-center mt-2')
            ], className="mb-3"),
            html.Div(
                [dbc.Label("Notes"), dbc.Textarea(id='checkpoint-notes', placeholder='Any observations or issues...')],
                className="mb-3"),
            dbc.Button(html.Span([html.I(className="fas fa-book-open me-2"), " Submit Log to Ledger"]),
                       id='checkpoint-btn', color='primary', className="w-100"),
            html.Div(id='checkpoint-output', className='mt-4')
        ])
    ])), lg=8, md=10), justify="center")


def monitor_layout():
    return html.Div([
        html.H2(html.Span([html.I(className="fas fa-satellite-dish me-2"), " Route & Ledger Monitor"])), html.Hr(),
        dbc.Row(dbc.Col(dcc.Dropdown(id='status-filter', options=[
            {'label': 'All', 'value': 'all'},
            {'label': 'In Transit', 'value': 'in_transit'},
            {'label': 'Completed', 'value': 'completed'},
            {'label': 'Overdue', 'value': 'overdue'}], value='all'), md=4), className="mb-4"),
        dbc.Row(dbc.Col(dcc.Loading(html.Div(id='route-monitoring-content')))),
        dcc.Interval(id='monitor-interval', interval=30 * 1000, n_intervals=0)
    ])


def receipt_layout():
    return dbc.Row(dbc.Col(dbc.Card(dbc.CardBody([
        html.H3(html.Span([html.I(className="fas fa-file-invoice me-2"), " Journey Report & Verification"])), html.Hr(),
        dcc.Dropdown(id='journey-select', placeholder='Select a completed journey to generate its verifiable report',
                     className="mb-4"),
        html.Div(id='receipt-content', className='text-center'),
        dcc.Download(id="download-pdf-component")
    ])), lg=8, md=10), justify="center")


# --- APPLICATION CALLBACKS ---

# Main router callback
@app.callback(Output('page-content', 'children'), Input('url', 'pathname'))
def display_page(pathname):
    if pathname == '/register': return register_layout()
    if pathname == '/checkpoint': return checkpoint_layout()
    if pathname == '/monitor': return monitor_layout()
    if pathname == '/receipt': return receipt_layout()
    return dashboard_layout()


# Dashboard Callbacks
@app.callback(
    [Output('active-transports', 'children'), Output('completed-today', 'children'),
     Output('overdue-transports', 'children'), Output('total-fuel', 'children')],
    Input('interval-component', 'n_intervals')
)
def update_kpis(n):
    with sqlite3.connect(DB_FILE) as conn:
        now, today_str = datetime.now(), datetime.now().strftime('%Y-%m-%d')
        overdue_threshold = (now - timedelta(days=3)).isoformat()
        active = conn.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'in_transit' AND created_at >= ?",
                              (overdue_threshold,)).fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'completed' AND DATE(created_at) = ?",
                                 (today_str,)).fetchone()[0]
        overdue = conn.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'in_transit' AND created_at < ?",
                               (overdue_threshold,)).fetchone()[0]
        total_fuel_query = conn.execute("SELECT SUM(fuel_volume) FROM vehicles WHERE status = 'in_transit'").fetchone()
        total_fuel = total_fuel_query[0] or 0
    return f"{active}", f"{completed}", f"{overdue}", f"{total_fuel:,.0f}"


@app.callback(
    [Output('transport-status-chart', 'figure'), Output('checkpoint-activity-chart', 'figure')],
    Input('interval-component', 'n_intervals')
)
def update_charts(n):
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query("SELECT status, created_at FROM vehicles", conn, parse_dates=['created_at'])
        df['status'] = df.apply(
            lambda r: 'overdue' if r['status'] == 'in_transit' and r['created_at'].to_pydatetime() < (
                        datetime.now() - timedelta(days=3)) else r['status'], axis=1)
        status_df = df.groupby('status').size().reset_index(name='count')
        activity_df = pd.read_sql_query(
            "SELECT checkpoint_name, COUNT(*) as count FROM checkpoints WHERE timestamp > date('now', '-1 day') GROUP BY checkpoint_name",
            conn)

    status_fig = px.pie(status_df, values='count', names='status', title='Transport Status Distribution',
                        color_discrete_map={'in_transit': '#2c3e50', 'completed': '#4E8575', 'overdue': '#DF691A'})
    activity_fig = px.bar(activity_df, x='checkpoint_name', y='count', title='Checkpoint Activity (Last 24 Hours)',
                          labels={'checkpoint_name': 'Checkpoint', 'count': 'Logins'})
    for fig in [status_fig, activity_fig]: fig.update_layout(paper_bgcolor='rgba(0,0,0,0)',
                                                             plot_bgcolor='rgba(0,0,0,0)', legend_title_text='')
    return status_fig, activity_fig


@app.callback(
    Output('active-transports-table', 'children'),
    Input('interval-component', 'n_intervals')
)
def update_active_transports_table(n):
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query(
            "SELECT plate_number, driver_name, origin, destination, fuel_volume, created_at, status FROM vehicles ORDER BY created_at DESC LIMIT 10",
            conn)
    if df.empty: return dbc.Alert("No recent journeys.", color="info")
    df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
    return dbc.Table.from_dataframe(df, striped=True, bordered=True, hover=True, responsive=True)


# Registration Callbacks
@app.callback(
    Output('output-passport-upload', 'children'),
    Input('upload-passport-image', 'contents'),
    State('upload-passport-image', 'filename')
)
def update_passport_output(contents, filename):
    if contents:
        return html.Div([html.Img(src=contents, style={'height': '100px'}), html.P(filename, className="small")])


@app.callback(
    Output("invoice-list-container", "children"),
    Input("invoice-help-target", "n_clicks")
)
def show_invoice_list(n_clicks):
    if not n_clicks: raise PreventUpdate
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query("SELECT invoice_number, amount_paid FROM payment_validation ORDER BY invoice_number",
                               conn)
    if df.empty: return html.P("No payment records found.")
    df['amount_paid'] = df['amount_paid'].apply(lambda x: f"${x:,.2f}")
    return dbc.Table.from_dataframe(df.rename(columns={"invoice_number": "Invoice #", "amount_paid": "Amount"}),
                                    striped=True, bordered=True, hover=True, size='sm')


@app.callback(
    Output('register-output', 'children'),
    Input('register-btn', 'n_clicks'),
    [State('plate-number', 'value'), State('driver-name', 'value'), State('driver-id', 'value'),
     State('driver-nationality', 'value'),
     State('upload-passport-image', 'contents'), State('upload-passport-image', 'filename'),
     State('company-name', 'value'), State('company-till', 'value'), State('invoice-number', 'value'),
     State('amount-paid', 'value'), State('origin', 'value'), State('destination', 'value'),
     State('fuel-volume', 'value')],
    prevent_initial_call=True
)
def register_vehicle(n, plate, name, drv_id, nat, pass_cont, pass_fname, co_name, co_till, inv_num, amt_paid, origin,
                     dest, vol):
    if not all([plate, name, drv_id, nat, pass_cont, co_name, co_till, inv_num, amt_paid, origin, dest, vol]):
        return dbc.Alert("Please fill all fields and upload passport image.", color="danger")
    if origin == dest: return dbc.Alert("Departure and Destination cannot be the same.", color="danger")

    with sqlite3.connect(DB_FILE) as conn:
        payment = conn.execute("SELECT amount_paid FROM payment_validation WHERE invoice_number = ?",
                               (inv_num,)).fetchone()
        if not payment or abs(payment[0] - float(amt_paid)) > 0.01:
            return dbc.Alert("Payment validation failed. Check invoice number and amount.", color="danger")

    pass_path = None
    if pass_cont:
        try:
            pass_dir = os.path.join('assets', 'passports')
            if not os.path.exists(pass_dir): os.makedirs(pass_dir)
            pass_path = os.path.join(pass_dir,
                                     f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{os.path.basename(pass_fname)}")
            with open(pass_path, 'wb') as f:
                f.write(base64.b64decode(pass_cont.split(',')[1]))
        except Exception as e:
            return dbc.Alert(f"Error saving passport image: {e}", color="danger")

    with sqlite3.connect(DB_FILE) as conn:
        try:
            h = generate_unique_hash(f"{plate}{name}{datetime.now()}")
            params = (
            plate.upper(), name, drv_id, nat, pass_path, co_name, co_till, inv_num, amt_paid, origin, dest, vol,
            datetime.now(), 'in_transit', h)
            conn.execute('''INSERT INTO vehicles (plate_number, driver_name, driver_id, driver_nationality, driver_passport_image_path,
                            company_name, company_till_number, invoice_number, amount_paid, origin, destination, fuel_volume, created_at, status, unique_hash)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', params)
            conn.commit()
            return dbc.Alert(html.Div([
                html.Strong("Success! Vehicle Registered."),
                html.P(f"Genesis Hash: {h}", className="small text-muted", style={'wordBreak': 'break-all'})
            ]), color="success")
        except sqlite3.IntegrityError:
            return dbc.Alert(f"Plate '{plate.upper()}' has an active journey.", color="danger")
        except Exception as e:
            return dbc.Alert(f"Database error: {e}", color="danger")


# Checkpoint Callbacks
@app.callback(
    Output('officer-select', 'options'),
    Input('checkpoint-location', 'value')
)
def update_officer_options(loc):
    if not loc: return []
    return [{'label': f"{r['name']} ({r['badge_number']})", 'value': r['name']} for _, r in
            get_officers_by_checkpoint(loc).iterrows()]


@app.callback(
    Output('output-checkpoint-image-upload', 'children'),
    Input('upload-checkpoint-image', 'contents'),
    State('upload-checkpoint-image', 'filename')
)
def update_checkpoint_image_output(contents, filename):
    if contents:
        return html.Div([html.Img(src=contents, style={'height': '100px'}), html.P(filename, className="small")])


@app.callback(
    Output('last-reading-info', 'children'),
    Input('cp-plate-number', 'value')
)
def update_last_reading_info(plate):
    if not plate: return [html.Strong("Enter vehicle plate number.")]
    with sqlite3.connect(DB_FILE) as conn:
        v = conn.execute("SELECT id, fuel_volume FROM vehicles WHERE plate_number = ? AND status = 'in_transit'",
                         (plate.upper(),)).fetchone()
        if not v: return dbc.Alert(f"No active journey for '{plate.upper()}'.", color="warning")
        v_id, init_fuel = v
        cp = conn.execute(
            "SELECT checkpoint_name, timestamp, fuel_volume_check FROM checkpoints WHERE vehicle_id = ? ORDER BY timestamp DESC LIMIT 1",
            (v_id,)).fetchone()
        if cp:
            ts = pd.to_datetime(cp[1]).strftime('%Y-%m-%d %H:%M')
            return [html.P(f"Last stop: {cp[0]} at {ts}"), html.H6(f"Last Fuel: {cp[2]:,.0f} L")]
        else:
            return [html.P("First checkpoint for this journey."), html.H6(f"Initial Fuel: {init_fuel:,.0f} L")]


def _submit_checkpoint_to_db(data):
    """Saves checkpoint image, then inserts the log into the database."""
    image_path = None
    if data.get('img_content'):
        try:
            content_type, content_string = data['img_content'].split(',')
            decoded = base64.b64decode(content_string)
            evidence_dir = os.path.join('assets', 'checkpoint_evidence')
            if not os.path.exists(evidence_dir):
                os.makedirs(evidence_dir)
            img_filename = f"evidence_{data['plate'].upper().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.PNG"
            image_path = os.path.join(evidence_dir, img_filename)
            with open(image_path, 'wb') as f:
                f.write(decoded)
        except Exception as e:
            print(f"Error saving checkpoint image: {e}")
            image_path = None

    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            v = c.execute(
                "SELECT id, destination, unique_hash FROM vehicles WHERE plate_number = ? AND status = 'in_transit'",
                (data['plate'].upper(),)).fetchone()
            if not v: return dbc.Alert("Vehicle not found or not in transit.", color="danger")
            v_id, dest, g_hash = v
            last_cp = c.execute(
                "SELECT signature_hash FROM checkpoints WHERE vehicle_id = ? ORDER BY timestamp DESC LIMIT 1",
                (v_id,)).fetchone()
            p_hash = last_cp[0] if last_cp else g_hash
            ts = datetime.now()
            s_hash = generate_unique_hash(
                f"{v_id}{data['loc']}{data['officer']}{ts}{data['fuel']}{data['notes']}{image_path or ''}{p_hash}")
            c.execute(
                'INSERT INTO checkpoints (vehicle_id, checkpoint_name, officer_name, timestamp, fuel_volume_check, notes, image_path, previous_hash, signature_hash) VALUES (?,?,?,?,?,?,?,?,?)',
                (v_id, data['loc'], data['officer'], ts, data['fuel'], data['notes'], image_path, p_hash, s_hash))
            msg, color = (f"Journey continues for {data['plate'].upper()}.", "info")
            if data['loc'] == dest:
                c.execute("UPDATE vehicles SET status = 'completed' WHERE id = ?", (v_id,));
                msg, color = "Final destination reached. Journey COMPLETED.", "success"
            conn.commit()
        return dbc.Alert(html.Div([
            html.Strong(msg),
            html.P(f"Checkpoint Hash: {s_hash}", className="small text-muted mt-2", style={'wordBreak': 'break-all'})
        ]), color=color)
    except Exception as e:
        return dbc.Alert(f"Database error: {e}", color="danger")


@app.callback(
    [Output('checkpoint-output', 'children', allow_duplicate=True),
     Output('confirmation-modal', 'is_open'),
     Output('confirm-modal-body', 'children'),
     Output('checkpoint-data-store', 'data'),
     Output('url', 'href', allow_duplicate=True)],
    Input('checkpoint-btn', 'n_clicks'),
    [State('cp-plate-number', 'value'), State('fuel-check', 'value'), State('checkpoint-location', 'value'),
     State('officer-select', 'value'), State('checkpoint-notes', 'value'),
     State('upload-checkpoint-image', 'contents')],
    prevent_initial_call=True)
def handle_initial_submit(n, plate, fuel, loc, officer, notes, img_content):
    if not all([plate, fuel, loc, officer]):
        return dbc.Alert("Please fill all required fields: Plate Number, Fuel Check, Location, and Officer.",
                         color="warning"), False, "", None, dash.no_update

    with sqlite3.connect(DB_FILE) as conn:
        v = conn.execute("SELECT id, fuel_volume FROM vehicles WHERE plate_number = ? AND status = 'in_transit'",
                         (plate.upper(),)).fetchone()
        if not v:
            return dbc.Alert(f"Vehicle '{plate.upper()}' not found or journey is not active.",
                             color="warning"), False, "", None, dash.no_update
        last_fuel = v[1]
        cp = conn.execute(
            "SELECT fuel_volume_check FROM checkpoints WHERE vehicle_id = ? ORDER BY timestamp DESC LIMIT 1",
            (v[0],)).fetchone()
        if cp: last_fuel = cp[0]

    try:
        fuel_float = float(fuel)
    except (ValueError, TypeError):
        return dbc.Alert("Fuel Volume Check must be a valid number.", color="warning"), False, "", None, dash.no_update

    discrepancy = last_fuel - fuel_float
    data_to_store = {'plate': plate, 'fuel': fuel_float, 'loc': loc, 'officer': officer, 'notes': notes,
                     'img_content': img_content}

    refresh_url = f'/checkpoint?refresh={datetime.now().timestamp()}'

    if discrepancy < -200 or discrepancy > 1500:
        modal_body = html.Div([
            dbc.Row(
                [dbc.Col(html.Strong("Last Recorded Fuel:")), dbc.Col(f"{last_fuel:,.1f} L", className="text-end")]),
            dbc.Row([dbc.Col(html.Strong("Current Reading:")), dbc.Col(f"{fuel_float:,.1f} L", className="text-end")]),
            html.Hr(),
            dbc.Row([dbc.Col(html.H5("Discrepancy:", className="fw-bold")),
                     dbc.Col(html.H5(f"{discrepancy:,.1f} L", className="text-danger fw-bold text-end"))]),
            html.P("This is a significant change. Please verify the reading and submit again if correct.",
                   className="mt-3")
        ])
        return dash.no_update, True, modal_body, data_to_store, dash.no_update

    alert = _submit_checkpoint_to_db(data_to_store)
    if alert.color in ["success", "info"]:
        return alert, False, "", None, refresh_url
    else:
        return alert, False, "", None, dash.no_update


@app.callback(
    [Output('checkpoint-output', 'children', allow_duplicate=True),
     Output('confirmation-modal', 'is_open', allow_duplicate=True),
     Output('url', 'href', allow_duplicate=True)],
    Input('submit-confirm-btn', 'n_clicks'),
    State('checkpoint-data-store', 'data'),
    prevent_initial_call=True
)
def handle_modal_submission(n, stored_data):
    if not n or not stored_data: raise PreventUpdate
    alert = _submit_checkpoint_to_db(stored_data)
    refresh_url = f'/checkpoint?refresh={datetime.now().timestamp()}'
    if alert.color in ["success", "info"]:
        return alert, False, refresh_url
    else:
        return alert, False, dash.no_update


@app.callback(
    Output('confirmation-modal', 'is_open', allow_duplicate=True),
    Input('cancel-confirm-btn', 'n_clicks'),
    prevent_initial_call=True
)
def close_confirmation_modal(n):
    return False


# Route Monitor Callbacks
@app.callback(
    Output('route-monitoring-content', 'children'),
    [Input('monitor-interval', 'n_intervals'), Input('status-filter', 'value')]
)
def update_route_monitoring(n, status_filter):
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query('SELECT * FROM vehicles', conn, parse_dates=['created_at'])
    df['calculated_status'] = df.apply(
        lambda r: 'overdue' if r['status'] == 'in_transit' and r['created_at'].to_pydatetime() < (
                    datetime.now() - timedelta(days=3)) else r['status'], axis=1)
    if status_filter != 'all': df = df[df['calculated_status'] == status_filter]
    if df.empty: return dbc.Alert("No vehicles match filter.", color="info", className="mt-4")

    cards = []
    for _, v in df.sort_values(by='created_at', ascending=False).iterrows():
        with sqlite3.connect(DB_FILE) as conn:
            cp_df = pd.read_sql_query('SELECT * FROM checkpoints WHERE vehicle_id = ? ORDER BY timestamp', conn,
                                      params=[v['id']])
        timeline = [dbc.ListGroupItem([html.Strong("Departure:"), f" {v['origin']} at {v['created_at']:%Y-%m-%d %H:%M}",
                                       html.Small(f" | Initial Fuel: {v['fuel_volume']:,.0f}L",
                                                  className="text-muted ms-2")])]
        last_fuel = v['fuel_volume']
        for i_cp, cp in cp_df.iterrows():
            discrepancy = last_fuel - cp['fuel_volume_check']
            last_fuel = cp['fuel_volume_check']
            if discrepancy < -50:
                color, tooltip_text = "warning", "Anomaly: Fuel volume INCREASED. Indicates potential measurement error or adulteration of fuel (e.g., adding water)."
            elif discrepancy > 1000:
                color, tooltip_text = "danger", "Critical Warning: Significant fuel loss detected. Indicates a potential major leak or large-scale siphoning."
            elif 250 < discrepancy <= 1000:
                color, tooltip_text = "warning", "Suspicious Loss: Fuel loss is higher than expected for transit. Monitor this pattern as it could indicate systematic skimming."
            else:
                color, tooltip_text = "secondary", "Normal variance: Represents expected fuel consumption."

            discrepancy_display = dbc.Badge(f"Δ: {discrepancy:,.0f}L", color=color, className="ms-2")
            tooltip_id = f"tip-{v['id']}-{i_cp}"
            timeline.append(dbc.ListGroupItem([html.Strong(f"✅ {cp['checkpoint_name']}"), html.Br(), html.Span(
                [html.Small(f"Fuel: {cp['fuel_volume_check']:,.0f}L", className="text-muted"),
                 html.Span(discrepancy_display, id=tooltip_id)]),
                                               dbc.Tooltip(tooltip_text, target=tooltip_id, placement="right")]))

        status_colors = {"completed": "success", "in_transit": "primary", "overdue": "danger"}
        cards.append(dbc.Card(dbc.CardBody([
            html.H4(html.Div([html.Span(f"🚛 {v['plate_number']}"),
                              dbc.Badge(v['calculated_status'].replace('_', ' ').title(),
                                        color=status_colors.get(v['calculated_status'], 'secondary'),
                                        className="ms-2")],
                             className="d-flex justify-content-between align-items-center"), className="card-title"),
            html.H6(f"{v['origin']} ➔ {v['destination']}", className="card-subtitle mb-2 text-muted"), html.Hr(),
            dbc.ListGroup(timeline, flush=True)
        ]), className="mb-3 shadow-sm"))
    return cards


# Receipt/Report Callbacks
@app.callback(
    Output('journey-select', 'options'),
    Input('url', 'pathname')
)
def update_journey_dropdown(pn):
    if pn != '/receipt': raise PreventUpdate
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query(
            "SELECT id, plate_number, destination, created_at FROM vehicles WHERE status = 'completed' ORDER BY created_at DESC",
            conn)
    return [{
                'label': f"{r['plate_number']} to {r['destination']} on {pd.to_datetime(r['created_at']).strftime('%Y-%m-%d')}",
                'value': r['id']} for _, r in df.iterrows()]


@app.callback(
    Output('receipt-content', 'children'),
    Input('journey-select', 'value')
)
def generate_receipt_view(j_id):
    if not j_id: return dbc.Alert("Select a journey to generate its report.", color="info")
    return dbc.Button(html.Span([html.I(className="fas fa-download me-2"), "Download Report"]), id="download-pdf-btn",
                      color="primary", size="lg")


@app.callback(
    Output("download-pdf-component", "data"),
    Input("download-pdf-btn", "n_clicks"),
    State("journey-select", "value"),
    prevent_initial_call=True
)
def download_pdf_report(n, j_id):
    if not j_id: raise PreventUpdate
    try:
        with sqlite3.connect(DB_FILE) as conn:
            plate = pd.read_sql_query("SELECT plate_number FROM vehicles WHERE id = ?", conn, params=[j_id]).iloc[0][
                'plate_number']

        pdf_bytes = create_journey_pdf(j_id)
        if pdf_bytes is None:
            print(f"Failed to generate PDF for journey ID {j_id}. Check logs for errors.")
            raise PreventUpdate

        filename = f"Report-{plate}-{datetime.now():%Y%m%d}.pdf"
        return dcc.send_bytes(pdf_bytes, filename)
    except Exception as e:
        print(f"Error in download_pdf_report callback: {e}")
        raise PreventUpdate


# --- Main Execution Block ---
if __name__ == '__main__':
    if not os.path.exists('assets'):
        os.makedirs('assets')
    if not os.path.exists(os.path.join('assets', 'checkpoint_evidence')):
        os.makedirs(os.path.join('assets', 'checkpoint_evidence'))

    init_database()
    seed_database()
    app.run(debug=True, port=5112)
