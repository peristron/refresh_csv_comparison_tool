import streamlit as st
import pandas as pd
import zipfile
import os

# --- Page Configuration ---
st.set_page_config(layout="wide", page_title="CSV Set Comparator")

# --- SECURITY: Simple Password Check ---
def check_password():
    """Returns `True` if the user had the correct password."""
    # If no password is set in secrets, allow access (Local Mode)
    if "app_password" not in st.secrets:
        return True

    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password
        st.text_input(
            "Please enter the access password:", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input again
        st.text_input(
            "Password incorrect. Please try again:", type="password", on_change=password_entered, key="password"
        )
        return False
    else:
        # Password correct
        return True

# --- HELPER FUNCTIONS ---
@st.cache_data
def get_file_list(zip_file):
    """ Simply returns list of CSV files in zip. """
    try:
        with zipfile.ZipFile(zip_file) as z:
            return sorted([f for f in z.namelist() if f.lower().endswith('.csv') and not f.startswith('__MACOSX')])
    except:
        return []

def normalize_filename(filename, prefix="", suffix_delimiter=""):
    """ Normalizes a filename to create a 'Match Key'. """
    base = os.path.basename(filename)
    name_no_ext = os.path.splitext(base)[0]
    
    # Remove Prefix
    if prefix and name_no_ext.startswith(prefix):
        name_no_ext = name_no_ext[len(prefix):]
    
    # Remove Suffix
    if suffix_delimiter and suffix_delimiter in name_no_ext:
        name_no_ext = name_no_ext.rsplit(suffix_delimiter, 1)[0]
        
    return name_no_ext

def read_csv_from_zip(zip_file, full_path):
    """ Robust CSV reader from Zip. """
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

# --- MAIN APP LOGIC ---

if check_password():
    st.title("📊 Refresh CSV Comparison Tool")

    # SIDEBAR CONFIGURATION
    with st.sidebar:
        st.header("1. Upload Files")
        zip_ref = st.file_uploader("Upload REFERENCE (Old) Zip", type="zip")
        zip_target = st.file_uploader("Upload TARGET (New) Zip", type="zip")

        st.divider()
        
        st.header("2. Auto-Match Logic")
        st.info("Look at the 'File Structure Preview' in the main window to decide what to enter here.")
        
        st.markdown("**Prefixes (Start of filename):**")
        ref_prefix = st.text_input("Remove from Old:", placeholder="e.g. kaplan-")
        tgt_prefix = st.text_input("Remove from New:", placeholder="e.g. newkaplan-")
        
        st.markdown("**Suffixes (End of filename):**")
        suffix_sep = st.text_input("Split character:", placeholder="e.g. _ or -")

        st.divider()
        
        st.header("3. Ignore Columns")
        global_ignore_str = st.text_area("Global Ignore:", "LoadDate, Timestamp, RunID")
        ignore_list = [x.strip() for x in global_ignore_str.split(',') if x.strip()]

    # MAIN BODY
    if zip_ref and zip_target:
        
        # 1. Get raw file lists
        ref_files_raw = get_file_list(zip_ref)
        tgt_files_raw = get_file_list(zip_target)

        # 2. FILE PREVIEWER (NEW FEATURE)
        with st.expander("📂 File Structure Preview (Click to see raw filenames)", expanded=True):
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.write("**Reference Zip Contents:**")
                st.write(ref_files_raw[:10]) # Show first 10
                if len(ref_files_raw) > 10: st.caption("...and more")
            with col_p2:
                st.write("**Target Zip Contents:**")
                st.write(tgt_files_raw[:10])
                if len(tgt_files_raw) > 10: st.caption("...and more")
            st.info("Use the filenames above to configure the 'Prefix' and 'Suffix' settings in the Sidebar.")

        # 3. Build Maps
        ref_map = {normalize_filename(f, ref_prefix, suffix_sep): f for f in ref_files_raw}
        tgt_map = {normalize_filename(f, tgt_prefix, suffix_sep): f for f in tgt_files_raw}
        
        common_keys = sorted(list(set(ref_map.keys()).intersection(set(tgt_map.keys()))))
        
        # 4. REPORTING
        st.divider()
        st.subheader(f"Global Status Report ({len(common_keys)} pairs auto-matched)")
        
        if common_keys:
            # Batch Comparison
            status_data = []
            progress_bar = st.progress(0)
            
            for i, key in enumerate(common_keys):
                f_ref = ref_map[key]
                f_tgt = tgt_map[key]
                
                d1 = read_csv_from_zip(zip_ref, f_ref)
                d2 = read_csv_from_zip(zip_target, f_tgt)
                
                status_msg, _ = compare_dataframes(d1, d2, ignore_list)
                
                status_data.append({
                    "Normalized Name": key,
                    "Status": status_msg,
                    "Old File": f_ref,
                    "New File": f_tgt
                })
                progress_bar.progress((i + 1) / len(common_keys))
            
            progress_bar.empty()
            
            df_summary = pd.DataFrame(status_data)
            def color_status(val):
                if 'Match' in val: return 'background-color: #d4edda'
                if 'Error' in val: return 'background-color: #f8d7da'
                return 'background-color: #fff3cd'
            
            st.dataframe(df_summary.style.applymap(color_status, subset=['Status']), use_container_width=True)
        else:
            st.warning("⚠️ No auto-matches found. Use the File Preview above to fix prefixes, or use the 'Manual Force-Pairing' tab below.")

        st.divider()

        # 5. DRILL DOWN / MANUAL TABS
        st.header("🔍 Detailed Inspection")
        
        tab_auto, tab_manual = st.tabs(["Auto-Matched Files", "Manual Force-Pairing"])
        
        with tab_auto:
            if common_keys:
                sel_key = st.selectbox("Select a pair to inspect:", common_keys)
                f_ref = ref_map[sel_key]
                f_tgt = tgt_map[sel_key]
                
                if st.button(f"Compare content: {sel_key}"):
                    d1 = read_csv_from_zip(zip_ref, f_ref)
                    d2 = read_csv_from_zip(zip_target, f_tgt)
                    status, diff_df = compare_dataframes(d1, d2, ignore_list)
                    
                    if status == "✅ Match":
                        st.success("Files match perfectly.")
                    elif status == "⚠️ Schema Diff":
                        st.error("Columns do not match.")
                    elif diff_df is not None:
                        st.warning(f"Found {len(diff_df)} rows with differences.")
                        removed = diff_df[diff_df['_source'] == 'OLD'].drop(columns=['_source'])
                        added = diff_df[diff_df['_source'] == 'NEW'].drop(columns=['_source'])
                        c1, c2 = st.columns(2)
                        c1.write("### Removed (Old Only)")
                        c1.dataframe(removed)
                        c2.write("### Added (New Only)")
                        c2.dataframe(added)
            else:
                st.info("No auto-matches to inspect.")

        with tab_manual:
            col_man1, col_man2 = st.columns(2)
            with col_man1:
                man_ref = st.selectbox("Select OLD File:", ref_files_raw)
            with col_man2:
                man_tgt = st.selectbox("Select NEW File:", tgt_files_raw)
                
            if st.button("Compare Selected Files"):
                d1 = read_csv_from_zip(zip_ref, man_ref)
                d2 = read_csv_from_zip(zip_target, man_tgt)
                status, diff_df = compare_dataframes(d1, d2, ignore_list)
                
                if status == "✅ Match": st.success("Match.")
                elif status == "⚠️ Schema Diff": st.error("Schema Mismatch.")
                elif diff_df is not None:
                    st.warning(f"Diff found: {len(diff_df)} rows.")
                    st.dataframe(diff_df)
    else:
        st.info("👈 Please start by uploading your zip files in the sidebar.")
