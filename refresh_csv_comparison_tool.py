import streamlit as st
import pandas as pd
import zipfile
import os

# --- 0. LOCAL CODE STORAGE (For User Download) ---
# This string contains the "Clean" version of the app (No password, local mode)
# Users can download this directly from the Sidebar.
LOCAL_SCRIPT_CONTENT = """
import streamlit as st
import pandas as pd
import zipfile
import os

st.set_page_config(layout="wide", page_title="CSV Set Comparator (Local)")

# --- HELPER FUNCTIONS ---
@st.cache_data
def get_file_list(zip_file):
    try:
        with zipfile.ZipFile(zip_file) as z:
            return sorted([f for f in z.namelist() if f.lower().endswith('.csv') and not f.startswith('__MACOSX')])
    except:
        return []

def normalize_filename(filename, prefix="", suffix_delimiter=""):
    base = os.path.basename(filename)
    name_no_ext = os.path.splitext(base)[0]
    if prefix and name_no_ext.startswith(prefix):
        name_no_ext = name_no_ext[len(prefix):]
    if suffix_delimiter and suffix_delimiter in name_no_ext:
        name_no_ext = name_no_ext.rsplit(suffix_delimiter, 1)[0]
    return name_no_ext

def read_csv_from_zip(zip_file, full_path):
    try:
        with zipfile.ZipFile(zip_file) as z:
            if z.getinfo(full_path).file_size == 0:
                return pd.DataFrame() 
            with z.open(full_path) as f:
                try:
                    return pd.read_csv(f)
                except pd.errors.EmptyDataError:
                    return pd.DataFrame()
                except UnicodeDecodeError:
                    f.seek(0)
                    return pd.read_csv(f, encoding='latin1')
    except Exception:
        return None

def compare_dataframes(df1, df2, ignore_cols):
    if df1 is None or df2 is None: return "❌ Error", None
    df1 = df1.drop(columns=[c for c in ignore_cols if c in df1.columns], errors='ignore')
    df2 = df2.drop(columns=[c for c in ignore_cols if c in df2.columns], errors='ignore')
    if set(df1.columns) != set(df2.columns): return "⚠️ Schema Diff", None
    df1 = df1.sort_index(axis=1); df2 = df2.sort_index(axis=1)
    df1['_source'] = 'OLD'; df2['_source'] = 'NEW'
    df_all = pd.concat([df1, df2], ignore_index=True)
    compare_cols = [c for c in df_all.columns if c != '_source']
    diff_df = df_all.drop_duplicates(subset=compare_cols, keep=False)
    if diff_df.empty: return "✅ Match", diff_df
    else: return "⚠️ Data Mismatch", diff_df

def display_diff_results(status, diff_df, rows_old, rows_new):
    m1, m2, m3 = st.columns(3)
    m1.metric("Rows in Old File", rows_old)
    m2.metric("Rows in New File", rows_new, delta=(rows_new - rows_old))
    if status == "✅ Match":
        m3.metric("Status", "Match")
        st.success("✅ Files match perfectly.")
    elif status == "⚠️ Schema Diff":
        m3.metric("Status", "Schema Diff", delta_color="inverse")
        st.error("⚠️ Column names do not match.")
    elif diff_df is not None:
        diff_count = len(diff_df)
        m3.metric("Rows with Differences", diff_count, delta_color="inverse")
        st.warning(f"⚠️ Found {diff_count} rows that differ.")
        removed = diff_df[diff_df['_source'] == 'OLD'].drop(columns=['_source'])
        added = diff_df[diff_df['_source'] == 'NEW'].drop(columns=['_source'])
        t1, t2 = st.tabs([f"Rows Removed ({len(removed)})", f"Rows Added ({len(added)})"])
        with t1: st.dataframe(removed, use_container_width=True)
        with t2: st.dataframe(added, use_container_width=True)

# --- MAIN APP ---
st.title("📊 Refresh CSV Comparison Tool")
with st.sidebar:
    st.header("1. Upload Files")
    zip_ref = st.file_uploader("Upload REFERENCE (Old) Zip", type="zip")
    zip_target = st.file_uploader("Upload TARGET (New) Zip", type="zip")
    st.divider()
    st.header("2. Auto-Match Logic")
    ref_prefix = st.text_input("Remove from Old:", placeholder="e.g. kaplan-")
    tgt_prefix = st.text_input("Remove from New:", placeholder="e.g. newkaplan-")
    suffix_sep = st.text_input("Split character:", placeholder="e.g. _ or -")
    st.divider()
    st.header("3. Ignore Columns")
    global_ignore_str = st.text_area("Global Ignore:", "LoadDate, Timestamp, RunID")
    ignore_list = [x.strip() for x in global_ignore_str.split(',') if x.strip()]

if zip_ref and zip_target:
    ref_files_raw = get_file_list(zip_ref); tgt_files_raw = get_file_list(zip_target)
    with st.expander("📂 File Structure Preview"):
        c1, c2 = st.columns(2)
        c1.write(ref_files_raw[:10]); c2.write(tgt_files_raw[:10])
    ref_map = {normalize_filename(f, ref_prefix, suffix_sep): f for f in ref_files_raw}
    tgt_map = {normalize_filename(f, tgt_prefix, suffix_sep): f for f in tgt_files_raw}
    common_keys = sorted(list(set(ref_map.keys()).intersection(set(tgt_map.keys()))))
    
    st.divider(); st.subheader(f"Global Status Report ({len(common_keys)} pairs)")
    if common_keys:
        status_data = []
        pbar = st.progress(0)
        for i, key in enumerate(common_keys):
            d1 = read_csv_from_zip(zip_ref, ref_map[key])
            d2 = read_csv_from_zip(zip_target, tgt_map[key])
            c_old = d1.shape[0] if d1 is not None else 0
            c_new = d2.shape[0] if d2 is not None else 0
            s_msg, d_df = compare_dataframes(d1, d2, ignore_list)
            status_data.append({"Name":key, "Status":s_msg, "Rows(Old)":c_old, "Rows(New)":c_new, "Diffs":len(d_df) if d_df is not None else 0})
            pbar.progress((i+1)/len(common_keys))
        pbar.empty()
        
        def color(v): 
            if 'Match' in v: return 'background-color:#d4edda'
            if 'Error' in v: return 'background-color:#f8d7da'
            return 'background-color:#fff3cd'
        st.dataframe(pd.DataFrame(status_data).style.applymap(color, subset=['Status']), use_container_width=True)
    
    st.divider(); st.header("🔍 Detailed Inspection")
    t1, t2 = st.tabs(["Auto-Matched", "Manual Force-Pairing"])
    with t1:
        if common_keys:
            k = st.selectbox("Select pair:", common_keys)
            if st.button(f"Compare: {k}"):
                d1 = read_csv_from_zip(zip_ref, ref_map[k]); d2 = read_csv_from_zip(zip_target, tgt_map[k])
                display_diff_results(*compare_dataframes(d1, d2, ignore_list), d1.shape[0] if d1 is not None else 0, d2.shape[0] if d2 is not None else 0)
    with t2:
        c1, c2 = st.columns(2)
        mr = c1.selectbox("Old File:", ref_files_raw); mt = c2.selectbox("New File:", tgt_files_raw)
        if st.button("Compare Selected"):
            d1 = read_csv_from_zip(zip_ref, mr); d2 = read_csv_from_zip(zip_target, mt)
            display_diff_results(*compare_dataframes(d1, d2, ignore_list), d1.shape[0] if d1 is not None else 0, d2.shape[0] if d2 is not None else 0)
else:
    st.info("👈 Please upload zip files to start.")
"""

# --- 1. CLOUD PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="CSV Set Comparator (Cloud)")

# --- 2. SECURITY CHECK ---
def check_password():
    """Returns `True` if the user had the correct password."""
    if "app_password" not in st.secrets:
        return True # Local mode fallback

    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Please enter the access password:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Password incorrect. Try again:", type="password", on_change=password_entered, key="password")
        return False
    else:
        return True

# --- 3. HELPER FUNCTIONS (Cloud Version) ---
@st.cache_data
def get_file_list(zip_file):
    try:
        with zipfile.ZipFile(zip_file) as z:
            return sorted([f for f in z.namelist() if f.lower().endswith('.csv') and not f.startswith('__MACOSX')])
    except:
        return []

def normalize_filename(filename, prefix="", suffix_delimiter=""):
    base = os.path.basename(filename)
    name_no_ext = os.path.splitext(base)[0]
    if prefix and name_no_ext.startswith(prefix):
        name_no_ext = name_no_ext[len(prefix):]
    if suffix_delimiter and suffix_delimiter in name_no_ext:
        name_no_ext = name_no_ext.rsplit(suffix_delimiter, 1)[0]
    return name_no_ext

def read_csv_from_zip(zip_file, full_path):
    try:
        with zipfile.ZipFile(zip_file) as z:
            if z.getinfo(full_path).file_size == 0:
                return pd.DataFrame() 
            with z.open(full_path) as f:
                try:
                    return pd.read_csv(f)
                except pd.errors.EmptyDataError:
                    return pd.DataFrame()
                except UnicodeDecodeError:
                    f.seek(0)
                    return pd.read_csv(f, encoding='latin1')
    except Exception:
        return None

def compare_dataframes(df1, df2, ignore_cols):
    """ Returns status and diff dataframe if any. """
    if df1 is None or df2 is None:
        return "❌ Error", None
        
    df1 = df1.drop(columns=[c for c in ignore_cols if c in df1.columns], errors='ignore')
    df2 = df2.drop(columns=[c for c in ignore_cols if c in df2.columns], errors='ignore')

    if set(df1.columns) != set(df2.columns):
        return "⚠️ Schema Diff", None

    df1 = df1.sort_index(axis=1)
    df2 = df2.sort_index(axis=1)
    
    df1['_source'] = 'OLD'
    df2['_source'] = 'NEW'
    
    df_all = pd.concat([df1, df2], ignore_index=True)
    compare_cols = [c for c in df_all.columns if c != '_source']
    
    diff_df = df_all.drop_duplicates(subset=compare_cols, keep=False)
    
    if diff_df.empty:
        return "✅ Match", diff_df
    else:
        return "⚠️ Data Mismatch", diff_df

def display_diff_results(status, diff_df, rows_old, rows_new):
    """ Helper to display metrics and tables in both Auto and Manual tabs """
    m1, m2, m3 = st.columns(3)
    m1.metric("Rows in Old File", rows_old)
    m2.metric("Rows in New File", rows_new, delta=(rows_new - rows_old))
    
    if status == "✅ Match":
        m3.metric("Status", "Match", delta_color="normal")
        st.success("✅ Files match perfectly (content is identical).")
    elif status == "⚠️ Schema Diff":
        m3.metric("Status", "Schema Diff", delta_color="inverse")
        st.error("⚠️ Column names do not match. Cannot compare data rows.")
    elif diff_df is not None:
        diff_count = len(diff_df)
        m3.metric("Rows with Differences", diff_count, delta_color="inverse")
        st.warning(f"⚠️ Found {diff_count} rows that differ.")
        
        removed = diff_df[diff_df['_source'] == 'OLD'].drop(columns=['_source'])
        added = diff_df[diff_df['_source'] == 'NEW'].drop(columns=['_source'])
        
        t1, t2 = st.tabs([f"Rows Removed ({len(removed)})", f"Rows Added ({len(added)})"])
        with t1: st.dataframe(removed, use_container_width=True)
        with t2: st.dataframe(added, use_container_width=True)

# --- 4. MAIN APP LOGIC ---

if check_password():
    st.title("📊 Refresh CSV Comparison Tool")

    with st.sidebar:
        # --- NEW SECTION: DOWNLOAD LOCAL CODE ---
        st.header("📥 Run Locally")
        with st.expander("Get Local Source Code"):
            st.info("Don't want to upload files here? Download the python script to run on your own machine.")
            st.download_button(
                label="Download Python Script",
                data=LOCAL_SCRIPT_CONTENT,
                file_name="local_csv_tool.py",
                mime="text/x-python"
            )
            st.markdown("""
            **How to run locally:**
            1. Install Python.
            2. Run: `pip install streamlit pandas`
            3. Run: `streamlit run local_csv_tool.py`
            """)
        
        st.divider()

        st.header("1. Upload Files")
        zip_ref = st.file_uploader("Upload REFERENCE (Old) Zip", type="zip")
        zip_target = st.file_uploader("Upload TARGET (New) Zip", type="zip")

        st.divider()
        st.header("2. Auto-Match Logic")
        st.markdown("**Prefixes:**")
        ref_prefix = st.text_input("Remove from Old:", placeholder="e.g. kaplan-")
        tgt_prefix = st.text_input("Remove from New:", placeholder="e.g. newkaplan-")
        st.markdown("**Suffixes:**")
        suffix_sep = st.text_input("Split character:", placeholder="e.g. _ or -")

        st.divider()
        st.header("3. Ignore Columns")
        global_ignore_str = st.text_area("Global Ignore:", "LoadDate, Timestamp, RunID")
        ignore_list = [x.strip() for x in global_ignore_str.split(',') if x.strip()]

    if zip_ref and zip_target:
        ref_files_raw = get_file_list(zip_ref)
        tgt_files_raw = get_file_list(zip_target)

        # File Preview
        with st.expander("📂 File Structure Preview (Click to view raw filenames)", expanded=False):
            c1, c2 = st.columns(2)
            c1.write("**Reference Zip:**"); c1.write(ref_files_raw[:10])
            c2.write("**Target Zip:**"); c2.write(tgt_files_raw[:10])

        # Build Maps
        ref_map = {normalize_filename(f, ref_prefix, suffix_sep): f for f in ref_files_raw}
        tgt_map = {normalize_filename(f, tgt_prefix, suffix_sep): f for f in tgt_files_raw}
        common_keys = sorted(list(set(ref_map.keys()).intersection(set(tgt_map.keys()))))
        
        # --- GLOBAL STATUS REPORT ---
        st.divider()
        st.subheader(f"Global Status Report ({len(common_keys)} pairs)")
        
        if common_keys:
            status_data = []
            progress_bar = st.progress(0)
            
            for i, key in enumerate(common_keys):
                f_ref = ref_map[key]
                f_tgt = tgt_map[key]
                
                d1 = read_csv_from_zip(zip_ref, f_ref)
                d2 = read_csv_from_zip(zip_target, f_tgt)
                
                count_old = d1.shape[0] if d1 is not None else 0
                count_new = d2.shape[0] if d2 is not None else 0
                
                status_msg, diff_df = compare_dataframes(d1, d2, ignore_list)
                count_diff = len(diff_df) if diff_df is not None else 0
                
                status_data.append({
                    "Normalized Name": key,
                    "Status": status_msg,
                    "Rows (Old)": count_old,
                    "Rows (New)": count_new,
                    "Diff Rows": count_diff if "Mismatch" in status_msg else 0,
                    "Old File": f_ref,
                    "New File": f_tgt
                })
                progress_bar.progress((i + 1) / len(common_keys))
            progress_bar.empty()
            
            df_summary = pd.DataFrame(status_data)
            cols = ["Normalized Name", "Status", "Rows (Old)", "Rows (New)", "Diff Rows", "Old File", "New File"]
            df_summary = df_summary[cols]

            def color_status(val):
                if 'Match' in val: return 'background-color: #d4edda'
                if 'Error' in val: return 'background-color: #f8d7da'
                return 'background-color: #fff3cd'
            
            st.dataframe(df_summary.style.applymap(color_status, subset=['Status']), use_container_width=True)
        else:
            st.warning("⚠️ No auto-matches found. Check settings.")

        st.divider()

        # --- DETAILED INSPECTION ---
        st.header("🔍 Detailed Inspection")
        tab_auto, tab_manual = st.tabs(["Auto-Matched Files", "Manual Force-Pairing"])
        
        with tab_auto:
            if common_keys:
                sel_key = st.selectbox("Select pair:", common_keys)
                if st.button(f"Compare: {sel_key}"):
                    d1 = read_csv_from_zip(zip_ref, ref_map[sel_key])
                    d2 = read_csv_from_zip(zip_target, tgt_map[sel_key])
                    
                    rows_old = d1.shape[0] if d1 is not None else 0
                    rows_new = d2.shape[0] if d2 is not None else 0
                    
                    status, diff_df = compare_dataframes(d1, d2, ignore_list)
                    display_diff_results(status, diff_df, rows_old, rows_new)
            else:
                st.info("No auto-matches.")

        with tab_manual:
            c1, c2 = st.columns(2)
            man_ref = c1.selectbox("Select OLD File:", ref_files_raw)
            man_tgt = c2.selectbox("Select NEW File:", tgt_files_raw)
                
            if st.button("Compare Selected Files"):
                d1 = read_csv_from_zip(zip_ref, man_ref)
                d2 = read_csv_from_zip(zip_target, man_tgt)
                
                rows_old = d1.shape[0] if d1 is not None else 0
                rows_new = d2.shape[0] if d2 is not None else 0
                
                status, diff_df = compare_dataframes(d1, d2, ignore_list)
                display_diff_results(status, diff_df, rows_old, rows_new)
    else:
        st.info("👈 Please upload zip files to start.")
