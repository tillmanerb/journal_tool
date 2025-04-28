import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, font as tkFont # Import font module
import sqlite3
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import os # To check if db exists
import collections # For defaultdict

# --- Database Setup ---
DB_NAME = "skill_journal.db"

def initialize_db():
    """Initializes the SQLite database and creates tables if they don't exist."""
    db_exists = os.path.exists(DB_NAME)
    # Enable type detection for timestamps
    conn = sqlite3.connect(DB_NAME, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    cursor = conn.cursor()

    # Enable Foreign Key support
    cursor.execute("PRAGMA foreign_keys = ON")

    if not db_exists:
        print("Database not found. Creating tables...")
        # Skills table: Add plan column
        cursor.execute('''
            CREATE TABLE Skills (
                skill_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                plan TEXT DEFAULT '' -- Added plan column
            )
        ''')

        # FormFields table
        cursor.execute('''
            CREATE TABLE FormFields (
                field_id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                field_type TEXT NOT NULL CHECK(field_type IN ('text', 'number', 'rating1-5')),
                deleted_timestamp timestamp DEFAULT NULL,
                UNIQUE(skill_id, field_name),
                FOREIGN KEY (skill_id) REFERENCES Skills (skill_id) ON DELETE CASCADE
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_formfields_active ON FormFields (skill_id, deleted_timestamp)")

        # Reflections table
        cursor.execute('''
            CREATE TABLE Reflections (
                reflection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_id INTEGER,
                timestamp timestamp NOT NULL,
                FOREIGN KEY (skill_id) REFERENCES Skills (skill_id) ON DELETE CASCADE
            )
        ''')

        # ReflectionEntries table
        cursor.execute('''
            CREATE TABLE ReflectionEntries (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                reflection_id INTEGER NOT NULL,
                field_id INTEGER NOT NULL,
                value TEXT,
                FOREIGN KEY (reflection_id) REFERENCES Reflections (reflection_id) ON DELETE CASCADE,
                FOREIGN KEY (field_id) REFERENCES FormFields (field_id) ON DELETE CASCADE
            )
        ''')

        # GenericReflections table
        cursor.execute('''
            CREATE TABLE GenericReflections (
                generic_reflection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp timestamp NOT NULL,
                content TEXT NOT NULL
            )
        ''')
        print("Tables created successfully.")
    else:
        # --- Simple Schema Check/Alteration ---
        print("Database found. Checking schemas...")
        # Check FormFields schema
        try:
            cursor.execute("PRAGMA table_info(FormFields)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'deleted_timestamp' not in columns:
                print("Adding 'deleted_timestamp' column to FormFields...")
                cursor.execute("ALTER TABLE FormFields ADD COLUMN deleted_timestamp timestamp DEFAULT NULL")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_formfields_active ON FormFields (skill_id, deleted_timestamp)")
                conn.commit()
                print("Column added to FormFields.")
            else:
                print("FormFields schema appears up-to-date.")
        except Exception as e:
            print(f"Error checking/altering FormFields table: {e}")

        # Check Skills schema for 'plan' column
        try:
            cursor.execute("PRAGMA table_info(Skills)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'plan' not in columns:
                print("Adding 'plan' column to Skills...")
                cursor.execute("ALTER TABLE Skills ADD COLUMN plan TEXT DEFAULT ''")
                conn.commit()
                print("Column 'plan' added to Skills.")
            else:
                print("Skills schema appears up-to-date.")
        except Exception as e:
            print(f"Error checking/altering Skills table: {e}")

        # Check timestamp column types (example for Reflections)
        try:
            cursor.execute("PRAGMA table_info(Reflections)")
            ts_type = next((info[2] for info in cursor.fetchall() if info[1] == 'timestamp'), None)
            if ts_type and ts_type.upper() != 'TIMESTAMP':
                 print(f"Warning: Reflections.timestamp type is {ts_type}, expected TIMESTAMP for proper date handling.")
        except Exception as e:
             print(f"Error checking Reflections table schema: {e}")


    conn.commit()
    conn.close()

# --- Database Helper Functions ---

def add_skill(name, description="", plan=""): # Added plan parameter
    """Adds a new skill to the database."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Include plan in insert statement
        cursor.execute("INSERT INTO Skills (name, description, plan) VALUES (?, ?, ?)", (name, description, plan))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", f"Skill '{name}' already exists.")
        return False
    except Exception as e:
        messagebox.showerror("Database Error", f"An error occurred adding skill: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_skills():
    """Retrieves all skills (ID and name) from the database."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Only select id and name here
        cursor.execute("SELECT skill_id, name FROM Skills ORDER BY name")
        skills = cursor.fetchall()
        return skills # Returns list of tuples (skill_id, name)
    except Exception as e:
        messagebox.showerror("Database Error", f"Could not fetch skills: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_skill_details(skill_id):
    """Retrieves name, description, and plan for a specific skill."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row # Access columns by name
        cursor = conn.cursor()
        cursor.execute("SELECT name, description, plan FROM Skills WHERE skill_id = ?", (skill_id,))
        details = cursor.fetchone()
        return details # Returns a Row object or None
    except Exception as e:
        messagebox.showerror("Database Error", f"Could not fetch skill details: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_skill_plan(skill_id, plan):
    """Updates the plan for a specific skill."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE Skills SET plan = ? WHERE skill_id = ?", (plan, skill_id))
        conn.commit()
        print(f"DB: Updated plan for skill_id {skill_id}")
        return True
    except Exception as e:
        if conn: conn.rollback()
        messagebox.showerror("Database Error", f"Could not update skill plan: {e}")
        return False
    finally:
        if conn:
            conn.close()

def add_form_field(skill_id, field_name, field_type):
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM FormFields WHERE skill_id = ? AND deleted_timestamp IS NULL", (skill_id,))
        count = cursor.fetchone()[0]
        if count >= 5:
            messagebox.showerror("Limit Reached", "A skill cannot have more than 5 active form fields.")
            return False
        cursor.execute("SELECT 1 FROM FormFields WHERE skill_id = ? AND field_name = ? AND deleted_timestamp IS NULL", (skill_id, field_name))
        if cursor.fetchone():
            messagebox.showerror("Error", f"An active field named '{field_name}' already exists for this skill.")
            return False
        cursor.execute("INSERT INTO FormFields (skill_id, field_name, field_type) VALUES (?, ?, ?)", (skill_id, field_name, field_type))
        conn.commit()
        return True
    except Exception as e:
        messagebox.showerror("Database Error", f"An error occurred adding form field: {e}")
        return False
    finally:
        if conn: conn.close()

def get_form_fields(skill_id, include_deleted=False):
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        cursor = conn.cursor()
        # Select field_type as well
        query = "SELECT field_id, field_name, field_type, deleted_timestamp FROM FormFields WHERE skill_id = ?"
        params = [skill_id]
        if not include_deleted: query += " AND deleted_timestamp IS NULL"
        query += " ORDER BY field_id"
        cursor.execute(query, params)
        fields = cursor.fetchall()
        return fields
    except Exception as e:
        messagebox.showerror("Database Error", f"Could not fetch form fields: {e}")
        return []
    finally:
        if conn: conn.close()

def delete_form_field(field_id):
    conn = None
    if not messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this field? It will be hidden but past entries using it will remain."): return False
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        now = datetime.now()
        cursor.execute("UPDATE FormFields SET deleted_timestamp = ? WHERE field_id = ?", (now, field_id))
        conn.commit()
        return True
    except Exception as e:
        if conn: conn.rollback()
        messagebox.showerror("Database Error", f"Could not delete form field: {e}")
        return False
    finally:
        if conn: conn.close()

def save_reflection(skill_id, entries):
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        now = datetime.now()
        cursor.execute("INSERT INTO Reflections (skill_id, timestamp) VALUES (?, ?)", (skill_id, now))
        reflection_id = cursor.lastrowid
        entry_data = [(reflection_id, field_id, value) for field_id, value in entries.items()]
        cursor.executemany("INSERT INTO ReflectionEntries (reflection_id, field_id, value) VALUES (?, ?, ?)", entry_data)
        conn.commit()
        return True
    except Exception as e:
        if conn: conn.rollback()
        messagebox.showerror("Database Error", f"Could not save skill reflection: {e}")
        return False
    finally:
        if conn: conn.close()

def save_generic_reflection(content):
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        now = datetime.now()
        cursor.execute("INSERT INTO GenericReflections (timestamp, content) VALUES (?, ?)", (now, content))
        conn.commit()
        return True
    except Exception as e:
        messagebox.showerror("Database Error", f"Could not save generic reflection: {e}")
        return False
    finally:
        if conn: conn.close()

def get_past_reflections(skill_id=None, limit=100):
    """Retrieves past reflections, including entry IDs for skill reflections."""
    print(f"Fetching past reflections (skill_id: {skill_id}, limit: {limit})")
    conn = None
    reflections_list = []
    try:
        conn = sqlite3.connect(DB_NAME, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Fetch Generic Reflections
        if skill_id is None:
            cursor.execute("SELECT generic_reflection_id as id, timestamp, content FROM GenericReflections ORDER BY timestamp DESC LIMIT ?", (limit,))
            for row in cursor.fetchall():
                reflections_list.append({'type': 'generic', 'id': row['id'], 'timestamp': row['timestamp'], 'content': row['content']})

        # Fetch Skill Reflections (get reflection_id)
        skill_query = "SELECT r.reflection_id as id, r.timestamp, s.name as skill_name, r.skill_id FROM Reflections r JOIN Skills s ON r.skill_id = s.skill_id"
        params = []
        if skill_id is not None:
            skill_query += " WHERE r.skill_id = ?"
            params.append(skill_id)
        skill_query += " ORDER BY r.timestamp DESC LIMIT ?"
        params.append(limit)
        cursor.execute(skill_query, params)
        skill_reflections = cursor.fetchall()

        # Fetch entries for each skill reflection
        for reflection_row in skill_reflections:
            entry_cursor = conn.cursor()
            # Fetch field_id, field_name, field_type, and value for each entry
            entry_cursor.execute("""
                SELECT re.entry_id, re.field_id, ff.field_name, ff.field_type, re.value
                FROM ReflectionEntries re
                JOIN FormFields ff ON re.field_id = ff.field_id
                WHERE re.reflection_id = ?
                ORDER BY ff.field_id
            """, (reflection_row['id'],))
            # Store entries as a list of dicts to preserve order and details
            entries_list = [dict(row) for row in entry_cursor.fetchall()]

            reflections_list.append({
                'type': 'skill',
                'id': reflection_row['id'], # This is reflection_id
                'skill_id': reflection_row['skill_id'],
                'timestamp': reflection_row['timestamp'],
                'skill_name': reflection_row['skill_name'],
                'entries': entries_list # List of dicts: [{'entry_id':.., 'field_id':.., 'field_name':.., 'field_type':.., 'value':..}, ...]
            })

        # Sort combined list if needed
        if skill_id is None:
            reflections_list.sort(key=lambda x: x['timestamp'], reverse=True)
            reflections_list = reflections_list[:limit]

        return reflections_list
    except Exception as e:
        messagebox.showerror("Database Error", f"Could not fetch past reflections: {e}")
        return []
    finally:
        if conn: conn.close()

def update_generic_reflection(generic_reflection_id, content):
    """Updates the content of a specific generic reflection."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE GenericReflections SET content = ? WHERE generic_reflection_id = ?",
                       (content, generic_reflection_id))
        conn.commit()
        print(f"DB: Updated generic reflection {generic_reflection_id}")
        return True
    except Exception as e:
        if conn: conn.rollback()
        messagebox.showerror("Database Error", f"Could not update generic reflection: {e}")
        return False
    finally:
        if conn: conn.close()

def update_skill_reflection_entry(entry_id, value):
    """Updates the value of a specific skill reflection entry."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE ReflectionEntries SET value = ? WHERE entry_id = ?", (value, entry_id))
        conn.commit()
        print(f"DB: Updated reflection entry {entry_id}")
        return True
    except Exception as e:
        if conn: conn.rollback()
        messagebox.showerror("Database Error", f"Could not update skill entry: {e}")
        return False
    finally:
        if conn: conn.close()

def delete_generic_reflection(generic_reflection_id):
    """Deletes a specific generic reflection."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM GenericReflections WHERE generic_reflection_id = ?", (generic_reflection_id,))
        conn.commit()
        print(f"DB: Deleted generic reflection {generic_reflection_id}")
        return True
    except Exception as e:
        if conn: conn.rollback()
        messagebox.showerror("Database Error", f"Could not delete generic reflection: {e}")
        return False
    finally:
        if conn: conn.close()

def delete_skill_reflection(reflection_id):
    """Deletes a specific skill reflection and its associated entries."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Foreign key cascade should handle deleting entries, but explicit delete is safer if cascade isn't guaranteed
        # cursor.execute("DELETE FROM ReflectionEntries WHERE reflection_id = ?", (reflection_id,))
        cursor.execute("DELETE FROM Reflections WHERE reflection_id = ?", (reflection_id,))
        conn.commit()
        print(f"DB: Deleted skill reflection {reflection_id} and its entries")
        return True
    except Exception as e:
        if conn: conn.rollback()
        messagebox.showerror("Database Error", f"Could not delete skill reflection: {e}")
        return False
    finally:
        if conn: conn.close()


def get_dashboard_data(skill_id=None):
    conn = None
    num_weeks = 5
    today = datetime.now().date()
    start_date = today - timedelta(days=today.weekday() + (num_weeks - 1) * 7)
    week_labels = []
    week_start_dates = []
    for i in range(num_weeks):
        week_start = start_date + timedelta(weeks=i)
        week_labels.append(f"Wk {week_start.strftime('%b %d')}")
        week_start_dates.append(week_start)
    weekly_counts = collections.OrderedDict((label, 0) for label in week_labels)
    try:
        conn = sqlite3.connect(DB_NAME, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        cursor = conn.cursor()
        base_query = "SELECT timestamp FROM {table} WHERE timestamp >= ?"
        params = [start_date]
        reflections_timestamps = []
        if skill_id is None or skill_id == "All": skill_query = base_query.format(table="Reflections")
        else:
            skill_query = base_query.format(table="Reflections") + " AND skill_id = ?"
            params.append(skill_id)
        cursor.execute(skill_query, params)
        reflections_timestamps.extend([row[0] for row in cursor.fetchall()])
        if skill_id is None or skill_id == "All":
            generic_params = [start_date]
            generic_query = base_query.format(table="GenericReflections")
            cursor.execute(generic_query, generic_params)
            reflections_timestamps.extend([row[0] for row in cursor.fetchall()])
        for ts in reflections_timestamps:
            if isinstance(ts, datetime):
                ts_date = ts.date()
                for i in range(num_weeks):
                    if week_start_dates[i] <= ts_date < week_start_dates[i] + timedelta(days=7):
                        weekly_counts[week_labels[i]] += 1; break
            else: print(f"Warning: Non-datetime timestamp: {ts} ({type(ts)})")
        cursor.execute("SELECT COUNT(*) FROM Reflections")
        skill_reflection_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM GenericReflections")
        generic_reflection_count = cursor.fetchone()[0]
        overall_count = skill_reflection_count + generic_reflection_count
        skill_aggregates = {}
        try:
            agg_query = "SELECT AVG(CAST(re.value AS REAL)) FROM ReflectionEntries re JOIN FormFields ff ON re.field_id = ff.field_id JOIN Reflections r ON re.reflection_id = r.reflection_id WHERE ff.field_name = 'Rating' AND ff.field_type = 'rating1-5' AND ff.deleted_timestamp IS NULL"
            agg_params = []
            agg_label = "Avg 'Rating' (All Skills)"
            if skill_id is not None and skill_id != "All":
                agg_query += " AND r.skill_id = ?"
                agg_params.append(skill_id)
                name_cursor = conn.cursor(); name_cursor.execute("SELECT name FROM Skills WHERE skill_id = ?", (skill_id,))
                skill_name_result = name_cursor.fetchone()
                agg_label = f"Avg 'Rating' ({skill_name_result[0]})" if skill_name_result else f"Avg 'Rating' (Skill ID: {skill_id})"
            cursor.execute(agg_query, agg_params)
            avg_rating_result = cursor.fetchone()
            if avg_rating_result and avg_rating_result[0] is not None: skill_aggregates[agg_label] = f"{avg_rating_result[0]:.2f}"
        except Exception as agg_e: print(f"Could not calculate aggregate 'Average Rating': {agg_e}")
        return {"overall_count": overall_count, "weekly_counts": weekly_counts, "skill_aggregates": skill_aggregates}
    except Exception as e:
        print(f"Error fetching dashboard data: {e}")
        return {"overall_count": 0, "weekly_counts": collections.OrderedDict(), "skill_aggregates": {}}
    finally:
        if conn: conn.close()


# --- GUI Application Class ---

class SkillJournalApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Skill Reflection Journal")
        self.root.geometry("850x700") # Adjusted size slightly for plan section

        # Style
        self.style = ttk.Style()
        self.style.theme_use('clam') # Using clam as TkinterModernThemes is not used here
        self.style.configure("Danger.TButton", foreground="red", font=('Arial', 8))

        # Main container frame
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Left Navigation Panel
        self.nav_frame = ttk.Frame(self.main_frame, width=150, relief=tk.RIDGE, padding=5)
        self.nav_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        ttk.Button(self.nav_frame, text="Dashboard", command=self.show_dashboard).pack(fill=tk.X, pady=5)
        ttk.Button(self.nav_frame, text="New Reflection", command=self.show_new_reflection_options).pack(fill=tk.X, pady=5)
        ttk.Button(self.nav_frame, text="View Reflections", command=self.show_view_reflections).pack(fill=tk.X, pady=5)
        ttk.Button(self.nav_frame, text="Manage Skills", command=self.show_manage_skills).pack(fill=tk.X, pady=5)

        # Right Content Panel
        self.content_frame = ttk.Frame(self.main_frame, relief=tk.RIDGE, padding=10)
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Dashboard Variables
        self.dashboard_skill_var = tk.StringVar()
        self.dashboard_fig = None
        self.dashboard_ax = None
        self.dashboard_canvas = None
        self.dashboard_canvas_widget = None
        self.dashboard_widgets = []

        # Show initial view
        self.show_dashboard()

    def clear_content_frame(self):
        """Destroys all widgets in the content frame."""
        for widget in self.content_frame.winfo_children(): widget.destroy()
        if self.dashboard_canvas_widget and not self.dashboard_canvas_widget.winfo_exists():
            self.dashboard_fig = None; self.dashboard_ax = None
            self.dashboard_canvas = None; self.dashboard_canvas_widget = None
        self.dashboard_widgets = []

    # --- View Functions ---

    def show_dashboard(self):
        """Displays the dashboard view."""
        self.clear_content_frame()
        title_label = ttk.Label(self.content_frame, text="Dashboard", font=("Arial", 16)); title_label.pack(pady=10)
        self.dashboard_widgets.append(title_label)
        controls_frame = ttk.Frame(self.content_frame); controls_frame.pack(fill=tk.X, padx=10, pady=5)
        self.dashboard_widgets.append(controls_frame)
        ttk.Label(controls_frame, text="Show Reflections For:").pack(side=tk.LEFT, padx=(0, 5))
        skills_list = [("All Reflections", "All")] + [(s[1], s[0]) for s in get_skills()]
        self.dashboard_skill_var = tk.StringVar()
        skill_dropdown = ttk.Combobox(controls_frame, textvariable=self.dashboard_skill_var, values=[s[0] for s in skills_list], state="readonly", width=25)
        skill_dropdown.pack(side=tk.LEFT, padx=5); skill_dropdown.set("All Reflections")
        self.dashboard_widgets.append(skill_dropdown)
        self.dashboard_skill_map = {name: id_val for name, id_val in skills_list}
        skill_dropdown.bind("<<ComboboxSelected>>", self.update_dashboard_chart)
        chart_frame = ttk.Frame(self.content_frame); chart_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.dashboard_widgets.append(chart_frame)
        try:
            self.dashboard_fig, self.dashboard_ax = plt.subplots(figsize=(7, 4))
            self.dashboard_canvas = FigureCanvasTkAgg(self.dashboard_fig, master=chart_frame)
            self.dashboard_canvas_widget = self.dashboard_canvas.get_tk_widget()
            self.dashboard_canvas_widget.pack(fill=tk.BOTH, expand=True)
        except ImportError:
             warning_label = ttk.Label(chart_frame, text="Matplotlib not installed.", foreground="red"); warning_label.pack(pady=20)
             self.dashboard_widgets.append(warning_label); self.dashboard_fig = None; self.dashboard_ax = None; self.dashboard_canvas = None
        except Exception as e:
             error_label = ttk.Label(chart_frame, text=f"Error initializing chart: {e}", foreground="red"); error_label.pack(pady=20)
             self.dashboard_widgets.append(error_label); self.dashboard_fig = None; self.dashboard_ax = None; self.dashboard_canvas = None
        stats_frame = ttk.Frame(self.content_frame); stats_frame.pack(fill=tk.X, padx=10, pady=(5, 0))
        self.dashboard_widgets.append(stats_frame)
        self.overall_count_label = ttk.Label(stats_frame, text="Total Reflections Logged: -"); self.overall_count_label.pack(anchor=tk.W, side=tk.LEFT, padx=5)
        self.dashboard_widgets.append(self.overall_count_label)
        self.aggregates_label = ttk.Label(stats_frame, text=""); self.aggregates_label.pack(anchor=tk.W, side=tk.RIGHT, padx=5)
        self.dashboard_widgets.append(self.aggregates_label)
        self.update_dashboard_chart()

    def update_dashboard_chart(self, event=None):
        """Updates the dashboard chart and stats."""
        if not all([self.dashboard_fig, self.dashboard_ax, self.dashboard_canvas]):
            print("Chart components not available, skipping update.")
            selected_skill_name = self.dashboard_skill_var.get(); skill_id = self.dashboard_skill_map.get(selected_skill_name, None)
            data = get_dashboard_data(skill_id=skill_id)
            self.overall_count_label.config(text=f"Total Reflections Logged: {data.get('overall_count', 0)}")
            agg_text = ", ".join([f"{k}: {v}" for k, v in data.get('skill_aggregates', {}).items()])
            self.aggregates_label.config(text=agg_text)
            return
        selected_skill_name = self.dashboard_skill_var.get(); skill_id = self.dashboard_skill_map.get(selected_skill_name, None)
        data = get_dashboard_data(skill_id=skill_id)
        weekly_counts = data.get('weekly_counts', collections.OrderedDict()); overall_count = data.get('overall_count', 0); aggregates = data.get('skill_aggregates', {})
        self.overall_count_label.config(text=f"Total Reflections Logged: {overall_count}")
        agg_text = ", ".join([f"{k}: {v}" for k, v in aggregates.items()]); self.aggregates_label.config(text=agg_text)
        self.dashboard_ax.clear()
        if weekly_counts:
            labels = list(weekly_counts.keys()); counts = list(weekly_counts.values())
            self.dashboard_ax.bar(labels, counts, color='skyblue')
            self.dashboard_ax.set_ylabel("Reflections Count"); self.dashboard_ax.set_title(f"Reflections per Week ({selected_skill_name}) - Last 5 Weeks")
            self.dashboard_ax.tick_params(axis='x', rotation=30, labelsize=8)
            max_count = max(counts) if counts else 0
            self.dashboard_ax.set_ylim(bottom=0, top=max(1, max_count * 1.1)); self.dashboard_ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
            self.dashboard_ax.spines['top'].set_visible(False); self.dashboard_ax.spines['right'].set_visible(False)
        else:
            self.dashboard_ax.text(0.5, 0.5, "No reflection data for this period/skill.", ha='center', va='center', transform=self.dashboard_ax.transAxes, color='grey')
            self.dashboard_ax.set_title(f"Reflections per Week ({selected_skill_name}) - Last 5 Weeks")
            self.dashboard_ax.set_xticks([]); self.dashboard_ax.set_yticks([])
            for spine in self.dashboard_ax.spines.values(): spine.set_visible(False)
        self.dashboard_fig.tight_layout(); self.dashboard_canvas.draw()

    def show_new_reflection_options(self):
        """Shows options for creating a new reflection."""
        self.clear_content_frame()
        ttk.Label(self.content_frame, text="New Reflection", font=("Arial", 16)).pack(pady=10)
        ttk.Button(self.content_frame, text="Generic Reflection", command=self.show_fill_generic_form).pack(pady=10)
        skills = get_skills()
        if skills:
            ttk.Label(self.content_frame, text="Reflect on a specific skill:").pack(pady=(10,0))
            skill_var = tk.StringVar()
            skill_names = [s[1] for s in skills]
            skill_dropdown = ttk.Combobox(self.content_frame, textvariable=skill_var, values=skill_names, state="readonly", width=30)
            skill_dropdown.pack(pady=5); skill_dropdown.set("Select Skill")
            def on_skill_select():
                selected_name = skill_var.get()
                if selected_name != "Select Skill":
                    selected_skill_id = next((s[0] for s in skills if s[1] == selected_name), None)
                    if selected_skill_id: self.show_fill_skill_form(selected_skill_id, selected_name)
                    else: messagebox.showerror("Error", "Could not find the selected skill ID.")
            ttk.Button(self.content_frame, text="Start Skill Reflection", command=on_skill_select).pack(pady=5)
        else:
            ttk.Label(self.content_frame, text="No skills defined yet. Go to 'Manage Skills' to add one.").pack(pady=10)

    def show_fill_generic_form(self):
        """Displays the form for filling out a generic reflection."""
        self.clear_content_frame()
        ttk.Label(self.content_frame, text="New Generic Reflection", font=("Arial", 16)).pack(pady=10)
        text_frame = ttk.Frame(self.content_frame); text_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        text_area = tk.Text(text_frame, height=15, width=60, wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_area.yview); text_area['yscrollcommand'] = scrollbar.set
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y); text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        def submit_generic():
            content = text_area.get("1.0", tk.END).strip()
            if content:
                if save_generic_reflection(content): messagebox.showinfo("Success", "Generic reflection saved!"); self.show_dashboard()
            else: messagebox.showwarning("Input Error", "Reflection content cannot be empty.")
        ttk.Button(self.content_frame, text="Save Reflection", command=submit_generic).pack(pady=10)

    def show_fill_skill_form(self, skill_id, skill_name):
        """Displays the dynamically generated form for a specific skill."""
        self.clear_content_frame()
        ttk.Label(self.content_frame, text=f"New Reflection: {skill_name}", font=("Arial", 16)).pack(pady=10)
        form_fields = get_form_fields(skill_id, include_deleted=False)
        if not form_fields:
             all_fields = get_form_fields(skill_id, include_deleted=True)
             msg = "No active form fields defined." if all_fields else "No form fields defined yet."
             ttk.Label(self.content_frame, text=f"{msg}\nGo to 'Manage Skills' -> 'Edit Form'.", foreground="orange").pack(pady=20)
             return
        if len(form_fields) > 5:
            ttk.Label(self.content_frame, text=f"Note: Showing {len(form_fields)} active fields (max 5 allowed).", foreground="blue").pack(pady=(0, 5))
            fields_to_display = form_fields[:5]
        else: fields_to_display = form_fields
        entry_widgets = {}
        fields_container = ttk.Frame(self.content_frame); fields_container.pack(fill=tk.X, padx=10, pady=5)
        for field_id, field_name, field_type, _ in fields_to_display:
             field_frame = ttk.Frame(fields_container); field_frame.pack(fill=tk.X, pady=4)
             ttk.Label(field_frame, text=f"{field_name}:", width=20, anchor=tk.W).pack(side=tk.LEFT, padx=(0, 5))
             widget = None; widget_var = None
             if field_type == 'text':
                 text_input_frame = ttk.Frame(field_frame); text_input_frame.pack(side=tk.LEFT, expand=True, fill=tk.X)
                 widget = tk.Text(text_input_frame, height=3, width=40, wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1)
                 widget.pack(side=tk.LEFT, expand=True, fill=tk.X); entry_widgets[field_id] = widget
             elif field_type == 'number':
                 widget_var = tk.StringVar(); widget = ttk.Entry(field_frame, textvariable=widget_var, width=15)
                 widget.pack(side=tk.LEFT); entry_widgets[field_id] = widget_var
             elif field_type == 'rating1-5':
                 widget_var = tk.StringVar(); widget = ttk.Combobox(field_frame, textvariable=widget_var, values=[str(i) for i in range(1, 6)], state="readonly", width=5)
                 widget.pack(side=tk.LEFT); entry_widgets[field_id] = widget_var
        def submit_skill_reflection():
            collected_entries = {}; valid = True
            for field_id, widget_ref in entry_widgets.items():
                value = None
                if isinstance(widget_ref, tk.StringVar): value = widget_ref.get()
                elif isinstance(widget_ref, tk.Text): value = widget_ref.get("1.0", tk.END).strip()
                field_info = next((f for f in fields_to_display if f[0] == field_id), None)
                if field_info:
                    field_name, field_type = field_info[1], field_info[2]
                    if not value and field_type != 'text': messagebox.showwarning("Input Error", f"Field '{field_name}' empty."); valid = False; break
                    if field_type == 'number' and value:
                        try: float(value)
                        except ValueError: messagebox.showwarning("Input Error", f"Field '{field_name}' not number."); valid = False; break
                if value is not None: collected_entries[field_id] = value
                else: print(f"Warning: Could not get value for field_id {field_id}")
            if valid and collected_entries:
                if save_reflection(skill_id, collected_entries): messagebox.showinfo("Success", f"Reflection saved!"); self.show_dashboard()
            elif valid and not collected_entries and fields_to_display:
                 if any(f[2] != 'text' for f in fields_to_display): pass
                 else:
                      if save_reflection(skill_id, collected_entries): messagebox.showinfo("Success", f"Reflection saved (empty)."); self.show_dashboard()
            elif not valid: pass
        ttk.Button(self.content_frame, text="Save Reflection", command=submit_skill_reflection).pack(pady=20)

    def show_view_reflections(self):
        """Displays past reflections with delete functionality."""
        self.clear_content_frame()
        ttk.Label(self.content_frame, text="View Past Reflections", font=("Arial", 16)).pack(pady=10)

        # --- Controls Frame (Filter + Delete Button) ---
        controls_frame = ttk.Frame(self.content_frame)
        controls_frame.pack(fill=tk.X, padx=10, pady=5)

        # Filter
        ttk.Label(controls_frame, text="Filter by Skill:").pack(side=tk.LEFT, padx=(0, 5))
        skills = [("All Skills", None)] + [(s[1], s[0]) for s in get_skills()]
        skill_filter_var = tk.StringVar()
        skill_filter_combo = ttk.Combobox(controls_frame, textvariable=skill_filter_var, values=[s[0] for s in skills], state="readonly", width=20)
        skill_filter_combo.pack(side=tk.LEFT, padx=5); skill_filter_combo.set("All Skills")

        # Delete Button (placed after the Treeview frame)

        # --- Treeview Frame ---
        tree_frame = ttk.Frame(self.content_frame); tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 0)) # Less bottom padding
        columns = ("timestamp", "type", "skill_or_content")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)
        tree.heading("timestamp", text="Date/Time"); tree.heading("type", text="Type"); tree.heading("skill_or_content", text="Skill / Content Snippet")
        tree.column("timestamp", width=150, anchor=tk.W); tree.column("type", width=80, anchor=tk.W); tree.column("skill_or_content", width=400, anchor=tk.W)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview); hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side='right', fill='y'); hsb.pack(side='bottom', fill='x'); tree.pack(side='left', fill='both', expand=True)
        self.reflections_tree = tree; self.loaded_reflections_data = []

        def populate_tree():
            """Fetches reflections and populates the tree."""
            selected_iid = tree.focus()
            selected_data = tree.item(selected_iid)['values'] if selected_iid else None
            for item in tree.get_children(): tree.delete(item)
            selected_skill_name = skill_filter_var.get(); selected_skill_id = next((s[1] for s in skills if s[0] == selected_skill_name), None)
            self.loaded_reflections_data = get_past_reflections(skill_id=selected_skill_id, limit=100)
            new_iid_to_select = None
            for i, reflection in enumerate(self.loaded_reflections_data):
                ts = reflection['timestamp']; formatted_ts = ts.strftime('%Y-%m-%d %H:%M') if isinstance(ts, datetime) else str(ts)
                rtype = reflection['type']
                if rtype == 'generic': content_snippet = (reflection['content'][:50] + '...') if len(reflection['content']) > 50 else reflection['content']; values = (formatted_ts, "Generic", content_snippet.replace("\n", " "))
                elif rtype == 'skill': values = (formatted_ts, "Skill", reflection['skill_name'])
                else: values = (formatted_ts, rtype, "N/A")
                iid = tree.insert("", tk.END, iid=i, values=values)
                if selected_data and values == selected_data: new_iid_to_select = iid
            if new_iid_to_select: tree.focus(new_iid_to_select); tree.selection_set(new_iid_to_select)

        def delete_selected_reflection():
            """Deletes the currently selected reflection in the treeview."""
            selected_item_id = tree.focus()
            if not selected_item_id:
                messagebox.showwarning("No Selection", "Please select a reflection to delete.")
                return

            try:
                reflection_index = int(selected_item_id)
                reflection_data = self.loaded_reflections_data[reflection_index]
                reflection_type = reflection_data['type']
                reflection_id = reflection_data['id'] # Generic or Skill reflection ID

                confirm_msg = f"Are you sure you want to permanently delete this {reflection_type} reflection?"
                if messagebox.askyesno("Confirm Delete", confirm_msg):
                    success = False
                    if reflection_type == 'generic':
                        success = delete_generic_reflection(reflection_id)
                    elif reflection_type == 'skill':
                        success = delete_skill_reflection(reflection_id)

                    if success:
                        messagebox.showinfo("Success", "Reflection deleted.")
                        populate_tree() # Refresh the list
                    # Else: Error message shown by delete function

            except (ValueError, IndexError, KeyError) as e:
                messagebox.showerror("Error", f"Could not delete reflection: {e}")


        # --- Delete Button (Placed below Treeview) ---
        delete_button_frame = ttk.Frame(self.content_frame)
        delete_button_frame.pack(pady=(5, 5), anchor=tk.E) # Anchor East
        delete_button = ttk.Button(delete_button_frame, text="Delete Selected Reflection", command=delete_selected_reflection, style="Danger.TButton")
        delete_button.pack()


        def show_reflection_details_popup(event=None):
            """Displays details of the selected reflection in a popup (with Edit button)."""
            selected_item_id = tree.focus()
            if not selected_item_id: return
            try:
                reflection_index = int(selected_item_id); reflection_data = self.loaded_reflections_data[reflection_index]
                details_window = tk.Toplevel(self.root); details_window.title("Reflection Details"); details_window.geometry("500x450")
                details_window.transient(self.root); details_window.grab_set()
                popup_frame = ttk.Frame(details_window, padding=10); popup_frame.pack(fill=tk.BOTH, expand=True)
                display_frame = ttk.Frame(popup_frame); display_frame.pack(fill=tk.BOTH, expand=True)
                ts_str = reflection_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if isinstance(reflection_data['timestamp'], datetime) else str(reflection_data['timestamp'])
                ttk.Label(display_frame, text=f"Timestamp: {ts_str}").pack(anchor=tk.W)
                ttk.Label(display_frame, text=f"Type: {reflection_data['type'].capitalize()}").pack(anchor=tk.W)
                content_widgets = {}
                if reflection_data['type'] == 'generic':
                    ttk.Label(display_frame, text="Content:", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(10, 2))
                    text_content_frame = ttk.Frame(display_frame); text_content_frame.pack(fill=tk.BOTH, expand=True)
                    content_text = tk.Text(text_content_frame, wrap=tk.WORD, height=15, relief=tk.SUNKEN, borderwidth=1); content_scrollbar = ttk.Scrollbar(text_content_frame, orient=tk.VERTICAL, command=content_text.yview); content_text['yscrollcommand'] = content_scrollbar.set
                    content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y); content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                    content_text.insert(tk.END, reflection_data['content']); content_text.config(state=tk.DISABLED)
                    content_widgets['main_text'] = content_text
                elif reflection_data['type'] == 'skill':
                    ttk.Label(display_frame, text=f"Skill: {reflection_data['skill_name']}", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(5, 2))
                    ttk.Label(display_frame, text="Entries:", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(5, 2))
                    entries_frame = ttk.Frame(display_frame); entries_frame.pack(fill=tk.BOTH, expand=True)
                    entry_widgets = {}
                    for entry in reflection_data['entries']:
                        entry_id = entry['entry_id']; field_name = entry['field_name']; field_type = entry['field_type']; value = entry['value']
                        entry_item_frame = ttk.Frame(entries_frame); entry_item_frame.pack(fill=tk.X, pady=2)
                        ttk.Label(entry_item_frame, text=f"{field_name}:", width=20, anchor=tk.W).pack(side=tk.LEFT, padx=(0, 5))
                        value_label = ttk.Label(entry_item_frame, text=value, wraplength=300); value_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
                        content_widgets[entry_id] = {'label': value_label, 'frame': entry_item_frame, 'field_type': field_type, 'current_value': value}
                button_frame = ttk.Frame(popup_frame); button_frame.pack(pady=10, fill=tk.X)
                edit_mode = tk.BooleanVar(value=False); edit_widgets_created = False
                def toggle_edit_mode():
                    nonlocal edit_widgets_created
                    if not edit_mode.get(): # Entering edit mode
                        edit_mode.set(True); edit_button.config(text="Cancel"); close_button.config(text="Save Changes", command=save_changes)
                        if reflection_data['type'] == 'generic': content_widgets['main_text'].config(state=tk.NORMAL); content_widgets['main_text'].focus()
                        elif reflection_data['type'] == 'skill':
                             if not edit_widgets_created:
                                 for entry_id, data in content_widgets.items():
                                     data['label'].pack_forget(); field_type = data['field_type']; current_value = data['current_value']; parent_frame = data['frame']; widget_ref = None
                                     if field_type == 'text': widget_ref = tk.Text(parent_frame, height=3, width=30, wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1); widget_ref.insert("1.0", current_value); widget_ref.pack(side=tk.LEFT, fill=tk.X, expand=True)
                                     elif field_type == 'number': var = tk.StringVar(value=current_value); widget_ref = ttk.Entry(parent_frame, textvariable=var, width=15); widget_ref.pack(side=tk.LEFT); widget_ref = var
                                     elif field_type == 'rating1-5': var = tk.StringVar(value=current_value); widget_ref = ttk.Combobox(parent_frame, textvariable=var, values=[str(i) for i in range(1, 6)], state="readonly", width=5); widget_ref.pack(side=tk.LEFT); widget_ref = var
                                     else: var = tk.StringVar(value=current_value); widget_ref = ttk.Entry(parent_frame, textvariable=var, state=tk.DISABLED); widget_ref.pack(side=tk.LEFT, fill=tk.X, expand=True); widget_ref = var
                                     data['edit_widget'] = widget_ref
                                 edit_widgets_created = True
                             else:
                                 for entry_id, data in content_widgets.items():
                                     data['label'].pack_forget(); widget_component = data['edit_widget']; actual_widget = None
                                     if isinstance(widget_component, tk.StringVar):
                                         for w in data['frame'].winfo_children():
                                             if isinstance(w, (ttk.Entry, ttk.Combobox)) and w.cget('textvariable') == str(widget_component): actual_widget = w; break
                                     elif isinstance(widget_component, tk.Text): actual_widget = widget_component
                                     if actual_widget: actual_widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
                    else: edit_mode.set(False); details_window.destroy() # Cancel closes window
                def save_changes():
                    if reflection_data['type'] == 'generic':
                        new_content = content_widgets['main_text'].get("1.0", tk.END).strip()
                        if new_content:
                            if update_generic_reflection(reflection_data['id'], new_content): messagebox.showinfo("Success", "Reflection updated.", parent=details_window); details_window.destroy(); populate_tree()
                        else: messagebox.showwarning("Input Error", "Content cannot be empty.", parent=details_window)
                    elif reflection_data['type'] == 'skill':
                        updates_successful = True
                        for entry_id, data in content_widgets.items():
                            widget_ref = data.get('edit_widget'); new_value = None
                            if isinstance(widget_ref, tk.StringVar): new_value = widget_ref.get()
                            elif isinstance(widget_ref, tk.Text): new_value = widget_ref.get("1.0", tk.END).strip()
                            if new_value is not None and new_value != data['current_value']:
                                if not update_skill_reflection_entry(entry_id, new_value): updates_successful = False; break
                        if updates_successful: messagebox.showinfo("Success", "Reflection entries updated.", parent=details_window); details_window.destroy(); populate_tree()
                edit_button = ttk.Button(button_frame, text="Edit", command=toggle_edit_mode); edit_button.pack(side=tk.LEFT, padx=5)
                close_button = ttk.Button(button_frame, text="Close", command=details_window.destroy); close_button.pack(side=tk.RIGHT, padx=5)
                details_window.update_idletasks()
                x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (details_window.winfo_width() // 2); y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (details_window.winfo_height() // 2)
                details_window.geometry(f"+{x}+{y}")
            except (ValueError, IndexError, KeyError, AttributeError) as e:
                messagebox.showerror("Error", f"Could not display details: {e}")
                if 'details_window' in locals() and details_window.winfo_exists(): details_window.destroy()

        tree.bind("<Double-1>", show_reflection_details_popup); tree.bind("<Return>", show_reflection_details_popup)
        refresh_button = ttk.Button(controls_frame, text="Refresh List", command=populate_tree); refresh_button.pack(side=tk.LEFT, padx=10)
        populate_tree()


    def show_manage_skills(self):
        """Displays the interface for managing skills."""
        self.clear_content_frame()
        ttk.Label(self.content_frame, text="Manage Skills", font=("Arial", 16)).pack(pady=10)
        add_frame = ttk.LabelFrame(self.content_frame, text="Add New Skill", padding=10); add_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(add_frame, text="Skill Name:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        new_skill_name_entry = ttk.Entry(add_frame, width=30); new_skill_name_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        ttk.Label(add_frame, text="Description (Optional):").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        new_skill_desc_entry = ttk.Entry(add_frame, width=40); new_skill_desc_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        add_frame.columnconfigure(1, weight=1)
        def submit_new_skill():
            name = new_skill_name_entry.get().strip(); desc = new_skill_desc_entry.get().strip()
            if name:
                if add_skill(name, desc, plan=""): new_skill_name_entry.delete(0, tk.END); new_skill_desc_entry.delete(0, tk.END); self.show_manage_skills()
            else: messagebox.showwarning("Input Error", "Skill name cannot be empty.")
        ttk.Button(add_frame, text="Add Skill", command=submit_new_skill).grid(row=2, column=0, columnspan=2, pady=10)
        list_frame = ttk.LabelFrame(self.content_frame, text="Existing Skills", padding=10); list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        skills = get_skills()
        if not skills: ttk.Label(list_frame, text="No skills added yet.").pack(pady=10)
        else:
            list_canvas = tk.Canvas(list_frame, borderwidth=0, highlightthickness=0); list_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=list_canvas.yview)
            scrollable_frame = ttk.Frame(list_canvas)
            scrollable_frame.bind("<Configure>", lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))
            def _on_mousewheel(event):
                 scroll_val = -1 if (event.num == 4 or event.delta > 0) else 1; list_canvas.yview_scroll(scroll_val, "units")
            list_canvas.bind("<MouseWheel>", _on_mousewheel); list_canvas.bind("<Button-4>", _on_mousewheel); list_canvas.bind("<Button-5>", _on_mousewheel)
            list_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw"); list_canvas.configure(yscrollcommand=list_scrollbar.set)
            list_canvas.pack(side="left", fill="both", expand=True); list_scrollbar.pack(side="right", fill="y")
            for skill_id, skill_name in skills:
                skill_item_frame = ttk.Frame(scrollable_frame); skill_item_frame.pack(fill=tk.X, pady=2, padx=5)
                ttk.Label(skill_item_frame, text=skill_name, width=30, anchor=tk.W).pack(side=tk.LEFT, padx=(0,5), fill=tk.X, expand=True)
                ttk.Button(skill_item_frame, text="Edit Form", command=lambda s_id=skill_id, s_name=skill_name: self.show_edit_skill_form(s_id, s_name)).pack(side=tk.LEFT, padx=5)

    def show_edit_skill_form(self, skill_id, skill_name):
        """Displays the interface for editing form fields and the skill plan."""
        self.clear_content_frame()
        ttk.Label(self.content_frame, text=f"Edit Form & Plan: {skill_name}", font=("Arial", 16)).pack(pady=10, anchor=tk.W)

        # --- Frame for Plan ---
        plan_frame = ttk.LabelFrame(self.content_frame, text="Skill Plan", padding=10)
        plan_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        skill_details = get_skill_details(skill_id)
        current_plan = skill_details['plan'] if skill_details and skill_details['plan'] else ""
        plan_text_area = tk.Text(plan_frame, height=5, width=60, wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1)
        plan_scrollbar = ttk.Scrollbar(plan_frame, orient=tk.VERTICAL, command=plan_text_area.yview); plan_text_area['yscrollcommand'] = plan_scrollbar.set
        plan_scrollbar.pack(side=tk.RIGHT, fill=tk.Y); plan_text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(0, 5))
        plan_text_area.insert("1.0", current_plan)
        def save_plan():
            new_plan = plan_text_area.get("1.0", tk.END).strip()
            if update_skill_plan(skill_id, new_plan): messagebox.showinfo("Success", "Skill plan updated successfully.")
        save_plan_button = ttk.Button(plan_frame, text="Save Plan", command=save_plan)
        save_plan_button.pack(pady=5) # Simple packing below

        # --- Frame to display current ACTIVE fields ---
        fields_frame = ttk.LabelFrame(self.content_frame, text="Active Fields", padding=10)
        fields_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        active_fields = get_form_fields(skill_id, include_deleted=False)
        if not active_fields: ttk.Label(fields_frame, text="No active fields defined yet.").pack(anchor=tk.W, padx=5, pady=5)
        else:
             for field_id, field_name, field_type, _ in active_fields:
                 field_item_frame = ttk.Frame(fields_frame); field_item_frame.pack(fill=tk.X, pady=2)
                 ttk.Label(field_item_frame, text=f"- {field_name} ({field_type})").pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X, anchor=tk.W)
                 ttk.Button(field_item_frame, text="Delete", style="Danger.TButton", command=lambda f_id=field_id: self.handle_delete_field(f_id, skill_id, skill_name)).pack(side=tk.RIGHT, padx=5)

        # --- Frame for adding a new field ---
        add_field_frame = ttk.LabelFrame(self.content_frame, text="Add New Field", padding=10)
        add_field_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        can_add_field = len(active_fields) < 5
        ttk.Label(add_field_frame, text="Field Name:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        new_field_name_entry = ttk.Entry(add_field_frame, width=30, state=tk.NORMAL if can_add_field else tk.DISABLED); new_field_name_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        ttk.Label(add_field_frame, text="Field Type:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        field_type_var = tk.StringVar()
        field_type_combo = ttk.Combobox(add_field_frame, textvariable=field_type_var, values=['text', 'number', 'rating1-5'], state="readonly" if can_add_field else tk.DISABLED)
        field_type_combo.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        if can_add_field: field_type_combo.set('text')
        add_field_frame.columnconfigure(1, weight=1)
        def submit_new_field():
            field_name = new_field_name_entry.get().strip(); field_type = field_type_var.get()
            if field_name and field_type:
                if add_form_field(skill_id, field_name, field_type): self.show_edit_skill_form(skill_id, skill_name) # Refresh view
            else: messagebox.showwarning("Input Error", "Field name and type cannot be empty.")
        add_field_button = ttk.Button(add_field_frame, text="Add Field", command=submit_new_field, state=tk.NORMAL if can_add_field else tk.DISABLED)
        add_field_button.grid(row=2, column=0, columnspan=2, pady=10)
        if not can_add_field: ttk.Label(add_field_frame, text="Maximum of 5 active fields reached.", foreground="red").grid(row=3, column=0, columnspan=2, pady=(0, 5))

        # --- Back button ---
        back_button = ttk.Button(self.content_frame, text="Back to Manage Skills", command=self.show_manage_skills)
        back_button.pack(pady=20, side=tk.BOTTOM, anchor=tk.SE) # Anchor South-East


    def handle_delete_field(self, field_id, skill_id, skill_name):
        """Calls the database function to delete and refreshes the view."""
        if delete_form_field(field_id):
            messagebox.showinfo("Success", "Field marked as deleted.")
            self.show_edit_skill_form(skill_id, skill_name) # Refresh


# --- Main Execution ---
if __name__ == "__main__":
    initialize_db()
    root = tk.Tk()
    app = SkillJournalApp(root)
    root.mainloop()
