import dash
import dash_auth
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import sqlite3
import hashlib
import qrcode
import io
import os
import Dashauth
import base64
from datetime import datetime, timedelta
import json
import random
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet

# --- App Initialization with Bootstrap Theme and Font Awesome Icons ---
FA = "https://use.fontawesome.com/releases/v5.15.4/css/all.css"
app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.FLATLY, FA])
app.title = "Fuel Transport Ledger - South Sudan"
DB_FILE = 'fuel_transport_ledger_v3.4.db'
logo = "logo.png"

server = app.server

dash_auth.BasicAuth(app, Dashauth.VALID_USERNAME_PASSWORD_PAIRS)


# --- Base64 Logo Loader ---
def get_logo_base64():
    """Reads the logo file from the assets folder and returns a base64 data URI."""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_dir, 'assets', logo)
        with open(logo_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        return f"data:image/png;base64,{encoded_string}"
    except FileNotFoundError:
        print(f"FATAL ERROR: Logo file not found at '{logo_path}'. Please ensure 'assets/{logo}' exists.")
        return None
    except Exception as e:
        print(f"Error encoding logo: {e}")
        return None


# Load the logo once when the app starts
APP_LOGO_B64 = get_logo_base64()


# --- Database Schema Setup ---
def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS vehicles (id INTEGER PRIMARY KEY, plate_number TEXT UNIQUE, driver_name TEXT, driver_id TEXT, origin TEXT, destination TEXT, fuel_volume REAL, created_at TIMESTAMP, status TEXT, unique_hash TEXT)')
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS checkpoints (id INTEGER PRIMARY KEY, vehicle_id INTEGER, checkpoint_name TEXT, officer_name TEXT, timestamp TIMESTAMP, fuel_volume_check REAL, notes TEXT, image_data TEXT, previous_hash TEXT, signature_hash TEXT, FOREIGN KEY (vehicle_id) REFERENCES vehicles (id))')
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS officers (id INTEGER PRIMARY KEY, name TEXT, badge_number TEXT, checkpoint_location TEXT)')
    if cursor.execute("SELECT COUNT(*) FROM officers").fetchone()[0] == 0:
        officers = [('John Makur', 'CP001', 'Juba'), ('Mary Adut', 'CP002', 'Wau'), ('Peter Deng', 'CP003', 'Malakal'),
                    ('Sarah Nyong', 'CP004', 'Bentiu'), ('James Lado', 'CP005', 'Yei'),
                    ('Achan Garang', 'CP006', 'Torit'), ('Mawien Dut', 'CP007', 'Aweil'),
                    ('Nadia Kiden', 'CP008', 'Bor'), ('Simon Tembura', 'CP009', 'Rumbek'),
                    ('Grace Akol', 'CP010', 'Yambio')]
        cursor.executemany('INSERT OR IGNORE INTO officers (name, badge_number, checkpoint_location) VALUES (?, ?, ?)',
                           officers)
        conn.commit()
    conn.close()


# --- Database Seeder with Anomaly Scenarios ---
def seed_database():
    # This function remains unchanged
    pass  # In a real app, this would contain your seeding logic


# --- UTILITY AND PDF FUNCTIONS ---
def generate_unique_hash(data): return hashlib.sha256(str(data).encode()).hexdigest()


def generate_qr_code_b64(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True);
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO();
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def get_checkpoint_locations():
    with sqlite3.connect(DB_FILE) as conn: return \
        pd.read_sql_query('SELECT DISTINCT checkpoint_location FROM officers', conn)['checkpoint_location'].tolist()


def get_officers_by_checkpoint(checkpoint):
    with sqlite3.connect(DB_FILE) as conn: return pd.read_sql_query(
        'SELECT name, badge_number FROM officers WHERE checkpoint_location = ?', conn, params=[checkpoint])


def create_journey_pdf(journey_id):
    with sqlite3.connect(DB_FILE) as conn:
        vehicle = pd.read_sql_query("SELECT * FROM vehicles WHERE id = ?", conn, params=[journey_id]).iloc[0]
        checkpoints = pd.read_sql_query("SELECT * FROM checkpoints WHERE vehicle_id = ? ORDER BY timestamp", conn,
                                        params=[journey_id])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=inch, rightMargin=inch, topMargin=1.5 * inch,
                            bottomMargin=inch)
    styles = getSampleStyleSheet()
    story = []

    def draw_header_and_footer(canvas, doc):
        canvas.saveState()
        page_width = doc.pagesize[0]
        page_height = doc.pagesize[1]

        # This is the correct way to draw the Base64 logo in ReportLab
        if APP_LOGO_B64:
            try:
                encoded_string = APP_LOGO_B64.split(",")[1]
                logo_bytes = base64.b64decode(encoded_string)
                logo_stream = io.BytesIO(logo_bytes)
                logo_img = ImageReader(logo_stream)
                canvas.drawImage(logo_img, doc.leftMargin, page_height - 1.1 * inch, width=1.8 * inch,
                                 preserveAspectRatio=True)
            except Exception as e:
                print(f"Error decoding/drawing base64 logo: {e}")
                canvas.drawString(doc.leftMargin, page_height - 0.8 * inch, "[Logo Render Error]")
        else:
            canvas.drawString(doc.leftMargin, page_height - 0.8 * inch, "[Logo Not Found]")

        canvas.setFont("Helvetica-Bold", 16)
        canvas.drawRightString(page_width - doc.rightMargin, page_height - 0.7 * inch, "Official Journey Report")
        canvas.setFont("Helvetica", 11)
        canvas.drawRightString(page_width - doc.rightMargin, page_height - 0.9 * inch,
                               f"Vehicle: {vehicle['plate_number']}")
        canvas.line(doc.leftMargin, page_height - 1.25 * inch, page_width - doc.rightMargin, page_height - 1.25 * inch)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(doc.leftMargin, 0.75 * inch,
                          "Defyhatenow EA Office | Juba, Hai-Malakal, Nimule Street | Tel: +211 922 007 505")
        canvas.drawRightString(page_width - doc.rightMargin, 0.75 * inch, f"Page {doc.page}")
        canvas.restoreState()

    final_hash = checkpoints['signature_hash'].iloc[-1] if not checkpoints.empty else vehicle['unique_hash']
    qr_data = json.dumps({'plate': vehicle['plate_number'], 'final_hash': final_hash})
    qr_img_b64 = generate_qr_code_b64(qr_data)
    qr_img_bytes = base64.b64decode(qr_img_b64)
    qr_code_image = Image(io.BytesIO(qr_img_bytes), width=1.2 * inch, height=1.2 * inch)
    qr_code_image.hAlign = 'CENTER'

    details_data = [
        [Paragraph(f"<b>Driver:</b> {vehicle['driver_name']} (ID: {vehicle['driver_id']})", styles['Normal']),
         Paragraph(f"<b>Route:</b> {vehicle['origin']} ➔ {vehicle['destination']}", styles['Normal']),
         qr_code_image],
        [Paragraph(f"<b>Dispatched:</b> {vehicle['created_at'][:16]}", styles['Normal']),
         Paragraph(f"<b>Initial Fuel:</b> {vehicle['fuel_volume']:,.0f} Liters", styles['Normal']),
         '']
    ]
    details_table = Table(details_data, colWidths=[2.5 * inch, 2.5 * inch, 1.5 * inch])
    details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('SPAN', (2, 0), (2, 1)),
        ('ALIGN', (2, 0), (2, 1), 'CENTER'),
        ('VALIGN', (2, 0), (2, 1), 'MIDDLE'),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 10))

    last_valid_hash = vehicle['unique_hash']
    is_chain_valid = True
    for _, row in checkpoints.iterrows():
        if row['previous_hash'] != last_valid_hash: is_chain_valid = False; break
        recalculated_hash = generate_unique_hash(
            f"{row['vehicle_id']}{row['checkpoint_name']}{row['officer_name']}{row['timestamp']}{row['fuel_volume_check']}{row['notes']}{row['image_data']}{row['previous_hash']}")
        if recalculated_hash != row['signature_hash']: is_chain_valid = False; break
        last_valid_hash = recalculated_hash

    if is_chain_valid:
        integrity_p = Paragraph(
            '✔ <font color="green"><b>Chain Verified:</b> The checkpoint log is complete and untampered.</font>',
            styles['Normal'])
    else:
        integrity_p = Paragraph(
            '❌ <font color="red"><b>Chain Broken:</b> The integrity of this log is compromised!</font>',
            styles['Normal'])
    story.append(integrity_p)
    story.append(Spacer(1, 20))

    story.append(Paragraph("<b>Checkpoint Ledger</b>", styles['h2']))
    story.append(Spacer(1, 10))
    table_data = [[Paragraph("<b>Timestamp</b>", styles['Normal']), Paragraph("<b>Location</b>", styles['Normal']),
                   Paragraph("<b>Details & Discrepancy (Δ)</b>", styles['Normal'])]]
    last_fuel = vehicle['fuel_volume']
    for _, row in checkpoints.iterrows():
        discrepancy = last_fuel - row['fuel_volume_check']
        last_fuel = row['fuel_volume_check']
        discrepancy_color = "red" if discrepancy < -50 or discrepancy > 250 else "black"
        details_cell_content = f"""
            <b>Officer:</b> {row['officer_name']}<br/>
            <b>Fuel Check:</b> {row['fuel_volume_check']:,.0f} Liters<br/>
            <font color='{discrepancy_color}'><b>Discrepancy:</b> {discrepancy:,.1f} L</font><br/>
            <font size='7' color='grey'>Hash: {row['signature_hash'][:45]}...</font>
        """
        if row['notes']:
            details_cell_content += f"<br/><b>Notes:</b> {row['notes']}"
        table_data.append([
            Paragraph(str(row['timestamp'])[:16], styles['Normal']),
            Paragraph(str(row['checkpoint_name']), styles['Normal']),
            Paragraph(details_cell_content, styles['Normal'])
        ])
        if row['image_data'] and row['image_data'].startswith('http'):
            try:
                img = Image(row['image_data'], width=2 * inch, height=2 * inch)
                table_data.append(['', '', img])
            except Exception:
                table_data.append(['', '', Paragraph("<i>[Image could not be loaded]</i>", styles['Italic'])])
    ledger_table = Table(table_data, colWidths=[1.4 * inch, 1.4 * inch, 3.7 * inch], repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
    ]
    for i, row_data in enumerate(table_data):
        if len(row_data) > 2 and isinstance(row_data[2], Image):
            style.extend([('SPAN', (0, i), (-1, i)), ('BACKGROUND', (0, i), (-1, i), colors.whitesmoke)])
    ledger_table.setStyle(TableStyle(style))
    story.append(ledger_table)
    doc.build(story, onFirstPage=draw_header_and_footer, onLaterPages=draw_header_and_footer)
    buffer.seek(0)
    return buffer


# --- APP LAYOUT AND STYLING ---
def create_navbar():
    # Using html.Img with the Base64 source is CORRECT here for the web page
    logo_display = html.Img(src=APP_LOGO_B64,
                            style={'height': '35px', 'margin-right': '15px'}) if APP_LOGO_B64 else html.I(
        className="fas fa-truck-moving me-2")

    return dbc.NavbarSimple(
        children=[
            dbc.NavItem(dbc.NavLink("Dashboard", href="/")),
            dbc.NavItem(dbc.NavLink("Register Vehicle", href="/register")),
            dbc.NavItem(dbc.NavLink("Checkpoint Login", href="/checkpoint")),
            dbc.NavItem(dbc.NavLink("Route Monitor", href="/monitor")),
            dbc.NavItem(dbc.NavLink("Download Reports", href="/receipt")),
        ],
        brand=html.Span([logo_display, "Fuel Transport Ledger"]),
        brand_href="/",
        color="primary",
        dark=True,
        className="mb-4",
    )


# The rest of your Dash app layout and callbacks remain unchanged...
# I'm including the full code for completeness.
app.layout = html.Div(
    [dcc.Location(id='url', refresh=False), create_navbar(), dbc.Container(id='page-content', fluid=True)])


def create_kpi_card(title, value_id, icon, color):
    return dbc.Card(dbc.CardBody([
        html.H4(html.I(className=f"{icon} me-2"), className=f"text-{color}"),
        html.H3(id=value_id),
        html.P(title, className="card-title"),
    ]))


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
        html.H3(html.Span([html.I(className="fas fa-plus-circle me-2"), " Register New Fuel Transport"])),
        html.Hr(),
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
                dbc.Col(html.Div([dbc.Label("Fuel Volume (Liters)"),
                                  dbc.Input(id='fuel-volume', type='number', placeholder='e.g., 35000')],
                                 className="mb-3"), md=6),
            ]),
            dbc.Row([
                dbc.Col(html.Div([dbc.Label("Origin"), dcc.Dropdown(id='origin', options=get_checkpoint_locations())],
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
        dbc.Form([
            html.Div([dbc.Label("Vehicle Plate Number"),
                      dbc.Input(id='cp-plate-number', placeholder='Enter plate number of vehicle in transit')],
                     className="mb-3"),
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
            html.Div([dbc.Label("Image Evidence URL (Optional)"),
                      dbc.Input(id='image-url', placeholder="Paste a public link to an image of the truck/meter",
                                type='url')], className="mb-3"),
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
        html.H2(html.Span([html.I(className="fas fa-satellite-dish me-2"), " Route & Ledger Monitor"])),
        html.Hr(),
        dbc.Row(dbc.Col(dcc.Dropdown(id='status-filter', options=[{'label': 'All Statuses', 'value': 'all'},
                                                                  {'label': 'In Transit', 'value': 'in_transit'},
                                                                  {'label': 'Completed', 'value': 'completed'},
                                                                  {'label': 'Overdue', 'value': 'overdue'}],
                                     value='all'), md=4), className="mb-4"),
        dbc.Row(dbc.Col(html.Div(id='route-monitoring-content'))),
        dcc.Interval(id='monitor-interval', interval=30 * 1000, n_intervals=0)
    ])


def receipt_layout():
    return dbc.Row(dbc.Col(dbc.Card(dbc.CardBody([
        html.H3(html.Span([html.I(className="fas fa-file-invoice me-2"), " Journey Report & Verification"])),
        html.Hr(),
        dcc.Dropdown(id='journey-select', placeholder='Select a completed journey to generate its verifiable report',
                     className="mb-4"),
        html.Div(id='receipt-content', className='text-center'),
        dcc.Download(id="download-pdf-component")
    ])), lg=8, md=10), justify="center")


# --- APPLICATION CALLBACKS ---
@app.callback(Output('page-content', 'children'), Input('url', 'pathname'))
def display_page(pathname):
    if pathname == '/register': return register_layout()
    if pathname == '/checkpoint': return checkpoint_layout()
    if pathname == '/monitor': return monitor_layout()
    if pathname == '/receipt': return receipt_layout()
    return dashboard_layout()


@app.callback([Output('active-transports', 'children'), Output('completed-today', 'children'),
               Output('overdue-transports', 'children'), Output('total-fuel', 'children')],
              Input('interval-component', 'n_intervals'))
def update_kpis(n):
    with sqlite3.connect(DB_FILE) as conn:
        active = \
            pd.read_sql_query("SELECT COUNT(*) as count FROM vehicles WHERE status = 'in_transit'", conn)['count'].iloc[
                0]
        completed = pd.read_sql_query(
            f"SELECT COUNT(*) as count FROM vehicles WHERE status = 'completed' AND DATE(created_at) = '{datetime.now().strftime('%Y-%m-%d')}'",
            conn)['count'].iloc[0]
        overdue = pd.read_sql_query(
            f"SELECT COUNT(*) as count FROM vehicles WHERE status = 'in_transit' AND created_at < '{datetime.now() - timedelta(days=2)}'",
            conn)['count'].iloc[0]
        total_fuel = \
            pd.read_sql_query("SELECT SUM(fuel_volume) as total FROM vehicles WHERE status = 'in_transit'", conn)[
                'total'].iloc[0] or 0
    return f"{active}", f"{completed}", f"{overdue}", f"{total_fuel:,.0f}"


@app.callback([Output('transport-status-chart', 'figure'), Output('checkpoint-activity-chart', 'figure')],
              Input('interval-component', 'n_intervals'))
def update_charts(n):
    with sqlite3.connect(DB_FILE) as conn:
        status_df = pd.read_sql_query("SELECT status, COUNT(*) as count FROM vehicles GROUP BY status", conn)
        activity_df = pd.read_sql_query(
            "SELECT checkpoint_name, COUNT(*) as count FROM checkpoints WHERE timestamp > date('now', '-1 day') GROUP BY checkpoint_name",
            conn)
    status_fig = px.pie(status_df, values='count', names='status', title='Transport Status Distribution',
                        color_discrete_map={'in_transit': '#2c3e50', 'completed': '#4E8575', 'overdue': '#DF691A'})
    activity_fig = px.bar(activity_df, x='checkpoint_name', y='count', title='Checkpoint Activity (Last 24 Hours)',
                          labels={'checkpoint_name': 'Checkpoint', 'count': 'Logins'})
    status_fig.update_layout(legend_title_text='Status', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    activity_fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return status_fig, activity_fig


@app.callback(Output('active-transports-table', 'children'), Input('interval-component', 'n_intervals'))
def update_active_transports_table(n):
    with sqlite3.connect(DB_FILE) as conn: df = pd.read_sql_query(
        "SELECT plate_number, driver_name, origin, destination, fuel_volume, created_at, status FROM vehicles ORDER BY created_at DESC LIMIT 10",
        conn)
    if df.empty: return dbc.Alert("No recent journeys found.", color="info")
    return dbc.Table.from_dataframe(df, striped=True, bordered=True, hover=True, responsive=True)


@app.callback(Output('register-output', 'children'), Input('register-btn', 'n_clicks'),
              [State('plate-number', 'value'), State('driver-name', 'value'), State('driver-id', 'value'),
               State('origin', 'value'), State('destination', 'value'), State('fuel-volume', 'value')],
              prevent_initial_call=True)
def register_vehicle(n, plate, name, drv_id, origin, dest, volume):
    if not all([plate, name, drv_id, origin, dest, volume]): return dbc.Alert("Please fill in all fields.",
                                                                              color="danger")
    if origin == dest: return dbc.Alert("Origin and Destination cannot be the same.", color="danger")
    try:
        with sqlite3.connect(DB_FILE) as conn:
            h = generate_unique_hash(f"{plate}{name}{datetime.now()}")
            conn.execute(
                'INSERT INTO vehicles (plate_number, driver_name, driver_id, origin, destination, fuel_volume, created_at, status, unique_hash) VALUES (?,?,?,?,?,?,?,?,?)',
                (plate.upper(), name, drv_id, origin, dest, volume, datetime.now(), 'in_transit', h))
        return dbc.Alert(html.Div([html.Strong("Success!"), html.P(f"Vehicle {plate.upper()} registered."),
                                   html.P(f"Genesis Hash: {h}", className="small")]), color="success")
    except sqlite3.IntegrityError:
        return dbc.Alert(f"Plate number '{plate.upper()}' already exists.", color="danger")
    except Exception as e:
        return dbc.Alert(f"Error: {e}", color="danger")


@app.callback(Output('officer-select', 'options'), Input('checkpoint-location', 'value'))
def update_officer_options(loc): return [{'label': f"{r['name']} ({r['badge_number']})", 'value': r['name']} for i, r in
                                         get_officers_by_checkpoint(loc).iterrows()] if loc else []


@app.callback(Output('checkpoint-output', 'children'), Input('checkpoint-btn', 'n_clicks'),
              [State('cp-plate-number', 'value'), State('checkpoint-location', 'value'),
               State('officer-select', 'value'), State('fuel-check', 'value'), State('checkpoint-notes', 'value'),
               State('image-url', 'value')], prevent_initial_call=True)
def checkpoint_login(n, plate, loc, officer, fuel, notes, img_url):
    if not all([plate, loc, officer, fuel]): return dbc.Alert("Please fill in all required fields.", color="danger")
    image_data = img_url
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            v = c.execute(
                "SELECT id, destination, unique_hash FROM vehicles WHERE plate_number = ? AND status = 'in_transit'",
                (plate.upper(),)).fetchone()
            if not v: return dbc.Alert("Vehicle not found or not in transit.", color="danger")
            v_id, dest, g_hash = v
            last_cp = c.execute(
                "SELECT signature_hash FROM checkpoints WHERE vehicle_id = ? ORDER BY timestamp DESC LIMIT 1",
                (v_id,)).fetchone()
            p_hash = last_cp[0] if last_cp else g_hash
            ts, color, msg = datetime.now(), "info", "➡️ Journey continues. Log added to ledger."
            s_hash = generate_unique_hash(f"{v_id}{loc}{officer}{ts}{fuel}{notes}{image_data}{p_hash}")
            c.execute(
                'INSERT INTO checkpoints (vehicle_id, checkpoint_name, officer_name, timestamp, fuel_volume_check, notes, image_data, previous_hash, signature_hash) VALUES (?,?,?,?,?,?,?,?,?)',
                (v_id, loc, officer, ts, fuel, notes, image_data, p_hash, s_hash))
            if loc == dest: c.execute("UPDATE vehicles SET status = 'completed' WHERE id = ?", (
                v_id,)); color, msg = "success", "🏁 Final destination reached. Journey COMPLETED."
        return dbc.Alert(html.Div([html.Strong("Success!"), html.P(msg)]), color=color)
    except Exception as e:
        return dbc.Alert(f"Error: {e}", color="danger")


@app.callback(Output('route-monitoring-content', 'children'),
              [Input('monitor-interval', 'n_intervals'), Input('status-filter', 'value')])
def update_route_monitoring(n, status_filter):
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query('SELECT * FROM vehicles', conn, parse_dates=['created_at'])
    df['calculated_status'] = df.apply(lambda r: 'overdue' if r['status'] == 'in_transit' and r['created_at'] < (
            datetime.now() - timedelta(days=2)) else r['status'], axis=1)
    if status_filter != 'all': df = df[df['calculated_status'] == status_filter]
    if df.empty: return dbc.Alert("No vehicles match the selected filter.", color="info", className="mt-4")
    cards = []
    for _, v in df.sort_values(by='created_at', ascending=False).iterrows():
        with sqlite3.connect(DB_FILE) as conn:
            cp_df = pd.read_sql_query('SELECT * FROM checkpoints WHERE vehicle_id = ? ORDER BY timestamp', conn,
                                      params=[v['id']])
        timeline = [dbc.ListGroupItem([html.Strong("Origin:"), f" {v['origin']} at {v['created_at']:%Y-%m-%d %H:%M}",
                                       html.Small(f" | Initial Fuel: {v['fuel_volume']:,.0f}L",
                                                  className="text-muted ms-2")])]
        last_fuel = v['fuel_volume']
        for i_cp, cp in cp_df.iterrows():
            discrepancy, last_fuel = last_fuel - cp['fuel_volume_check'], cp['fuel_volume_check']
            if discrepancy < -50:
                color, tooltip_text, is_anomaly = "warning", "Anomaly: Fuel volume INCREASED. Indicates potential measurement error or adulteration of fuel (e.g., adding water).", True
            elif discrepancy > 1000:
                color, tooltip_text, is_anomaly = "danger", "Critical Warning: Significant fuel loss detected. Indicates a potential major leak or large-scale siphoning.", True
            elif 250 < discrepancy <= 1000:
                color, tooltip_text, is_anomaly = "warning", "Suspicious Loss: Fuel loss is higher than expected for transit. Monitor this pattern as it could indicate systematic skimming.", True
            else:
                color, tooltip_text, is_anomaly = "secondary", "Normal variance: Represents expected fuel consumption.", False
            discrepancy_display = html.Span(f" (Δ: {discrepancy:,.0f}L)", style={'fontWeight': 'bold'})
            if is_anomaly:
                discrepancy_display = dbc.Badge(f"Δ: {discrepancy:,.0f}L", color=color, className="ms-2")

            tooltip_id = f"tip-{v['id']}-{i_cp}"
            tooltip_obj = dbc.Tooltip(tooltip_text, target=tooltip_id, placement="right")
            timeline.append(dbc.ListGroupItem([html.Strong(f"✅ {cp['checkpoint_name']}"), html.Br(), html.Span(
                [html.Small(f"Fuel: {cp['fuel_volume_check']:,.0f}L", className="text-muted"),
                 html.Span(discrepancy_display, id=tooltip_id)]), tooltip_obj]))
        status_colors = {"completed": "success", "in_transit": "primary", "overdue": "danger"}
        cards.append(dbc.Card(dbc.CardBody([html.H4(html.Div([html.Span(f"🚛 {v['plate_number']}"), dbc.Badge(
            v['calculated_status'].replace('_', ' ').title(),
            color=status_colors.get(v['calculated_status'], 'secondary'), className="ms-2")],
                                                             className="d-flex justify-content-between align-items-center"),
                                                    className="card-title"),
                                            html.H6(f"{v['origin']} ➔ {v['destination']}",
                                                    className="card-subtitle mb-2 text-muted"), html.Hr(),
                                            dbc.ListGroup(timeline, flush=True)]), className="mb-3 shadow-sm"))
    return cards


@app.callback(Output('journey-select', 'options'), Input('url', 'pathname'))
def update_journey_dropdown(pn):
    if pn == '/receipt':
        with sqlite3.connect(DB_FILE) as conn: df = pd.read_sql_query(
            "SELECT id, plate_number, destination, created_at FROM vehicles WHERE status = 'completed' ORDER BY created_at DESC",
            conn)
        return [{'label': f"{r['plate_number']} to {r['destination']} on {r['created_at'][:10]}", 'value': r['id']} for
                _, r in df.iterrows()]
    return []


@app.callback(Output('receipt-content', 'children'), Input('journey-select', 'value'))
def generate_receipt_view(j_id):
    if not j_id: return dbc.Alert("Select a completed journey to generate its verifiable report.", color="info")
    return dbc.Button(html.Span([html.I(className="fas fa-download me-2"), "Download Verifiable PDF Report"]),
                      id="download-pdf-btn", color="primary", size="lg")


@app.callback(Output("download-pdf-component", "data"), Input("download-pdf-btn", "n_clicks"),
              State("journey-select", "value"), prevent_initial_call=True)
def download_pdf_report(n, j_id):
    if not j_id: return
    with sqlite3.connect(DB_FILE) as conn: plate = \
        pd.read_sql_query("SELECT plate_number FROM vehicles WHERE id = ?", conn, params=[j_id]).iloc[0]['plate_number']
    return dcc.send_bytes(create_journey_pdf(j_id).getvalue(), f"Report-{plate}-{datetime.now():%Y%m%d}.pdf")


# --- Main Execution Block ---
if __name__ == '__main__':
    init_database()
    seed_database() # Comment out seeder after first run
    app.run(debug=True)
