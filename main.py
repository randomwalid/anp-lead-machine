import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime
from apify_client import ApifyClient
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(
    page_title="ANP Partners | Lead Machine",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');

    /* --- GLOBAL RESET --- */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #150d2e;
    }

    /* --- BACKGROUNDS (Targeting ALL Streamlit containers) --- */
    .stApp {
        background-color: #fff1e6 !important;
    }

    /* The main content area */
    .main .block-container {
        background-color: #fff1e6 !important;
        padding-top: 2rem !important; /* Reduce top padding to hide header gap */
    }

    /* THE HEADER (The pesky top bar) */
    header, header[data-testid="stHeader"], .st-emotion-cache-12fmw14 {
        background-color: #fff1e6 !important;
        z-index: 1 !important;
    }

    /* HIDE HAMBURGER MENU & FOOTER */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;} /* Hides the "Deploy" button if visible */

    /* --- SIDEBAR --- */
    section[data-testid="stSidebar"] {
        background-color: #f8e8e7 !important;
        border-right: 1px solid #efd9ce;
    }

    /* Remove gradient on sidebar top */
    section[data-testid="stSidebar"] > div {
        background-color: #f8e8e7 !important;
    }

    /* --- WIDGETS (Inputs, Tables, etc.) --- */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"], div[data-testid="stDataFrame"] {
        background-color: #ffffff !important;
        color: #150d2e !important;
        border: 1px solid #e0d2f8 !important;
        border-radius: 8px;
    }

    /* HEADERS & LABELS */
    h1, h2, h3, h4, h5, p, label, .stMarkdown {
        color: #150d2e !important;
    }

    /* BUTTONS */
    div.stButton > button {
        background-color: #b79ced !important;
        color: #150d2e !important;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        transition: opacity 0.2s;
    }
    div.stButton > button:hover {
        opacity: 0.9;
        border: 1px solid #150d2e !important;
    }

    /* SPINNER TEXT */
    .stSpinner > div > div {
        border-top-color: #b79ced !important;
    }
</style>
""", unsafe_allow_html=True)

def get_apify_history():
    """Fetch the last 10 successful runs from Apify"""
    try:
        api_token = os.getenv("APIFY_API_TOKEN")
        if not api_token:
            return []
        
        client = ApifyClient(api_token)
        
        try:
            runs_response = client.runs().list(limit=10, desc=True)
            items = runs_response.get("items", []) if isinstance(runs_response, dict) else []
        except:
            items = []
        
        history = []
        for run in items:
            if run.get("status") == "SUCCEEDED":
                run_id = run.get("id")
                started_at = run.get("startedAt", "")
                
                search_term = "Search"
                if run.get("input"):
                    search_array = run["input"].get("searchStringsArray", [])
                    if search_array:
                        search_term = search_array[0]
                
                try:
                    date = datetime.fromisoformat(started_at.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
                except:
                    date = started_at[:10] if started_at else "Unknown"
                
                history.append({
                    "id": run_id,
                    "label": f"{search_term} ({date})",
                    "dataset_id": run.get("defaultDatasetId"),
                    "search_term": search_term
                })
        
        return history
    except:
        return []

def load_dataset_from_apify(dataset_id):
    """Load results from a specific Apify dataset"""
    try:
        api_token = os.getenv("APIFY_API_TOKEN")
        if not api_token:
            return None
        
        client = ApifyClient(api_token)
        items = list(client.dataset(dataset_id).iterate_items())
        
        if not items:
            return None
        
        processed_items = []
        for item in items:
            processed_items.append({
                "title": item.get("title"),
                "address": item.get("address"),
                "phone": item.get("phone") or item.get("phoneNumber"),
                "website": item.get("website") or None,
                "totalScore": item.get("totalScore"),
                "reviewsCount": item.get("reviewsCount"),
                "url": item.get("url"),
            })
        
        df = pd.DataFrame(processed_items)
        
        if "website" in df.columns:
            df["website"] = df["website"].replace("", None)
        
        return df
    except Exception as e:
        st.error(f"Erreur lors du chargement du dataset: {str(e)}")
        return None

def export_to_sheets(dataframe, sheet_name):
    """Export data to Google Sheets"""
    try:
        creds_json = os.getenv("GOOGLE_CREDENTIALS")
        if not creds_json:
            return False, "❌ GOOGLE_CREDENTIALS non configuré."
        
        creds_dict = json.loads(creds_json)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        gc = gspread.authorize(creds)
        
        try:
            spreadsheet = gc.open(sheet_name)
        except gspread.SpreadsheetNotFound:
            return False, "⚠️ Impossible de trouver le fichier. Vérifiez le nom et le partage."
        
        sheet = spreadsheet.sheet1
        
        existing_data = sheet.get_all_values()
        
        if len(existing_data) == 0:
            headers = ["Nom", "Adresse", "Téléphone", "Site Web", "Note", "Avis"]
            sheet.append_row(headers)
        
        for _, row in dataframe.iterrows():
            row_data = [
                str(row.get("title", "") or ""),
                str(row.get("address", "") or ""),
                str(row.get("phone", "") or ""),
                str(row.get("website", "") or ""),
                str(row.get("totalScore", "") or ""),
                str(row.get("reviewsCount", "") or ""),
            ]
            sheet.append_row(row_data)
        
        return True, f"✅ {len(dataframe)} leads ajoutés à la base de données !"
        
    except json.JSONDecodeError:
        return False, "❌ Format GOOGLE_CREDENTIALS invalide."
    except Exception as e:
        return False, f"❌ Erreur: {str(e)}"

with st.sidebar:
    st.markdown("## 🎯 ANP Partners")
    st.markdown("### Lead Machine")
    st.markdown("---")
    
    search_query = st.text_input(
        "🔍 Requête de recherche",
        placeholder="Ex: Avocats Paris 15",
        help="Entrez votre recherche Google Maps"
    )
    
    max_results = st.number_input(
        "📊 Nombre max de résultats",
        min_value=1,
        max_value=100,
        value=20,
        help="Maximum 100 résultats"
    )
    
    sheet_name = st.text_input(
        "📁 Nom du Fichier Google Sheets",
        value="ANP_prospects_database",
        help="Nom exact du fichier Google Sheets partagé"
    )
    
    run_scraping = st.button("🚀 Lancer le Scraping", type="primary", use_container_width=True)
    
    st.markdown("---")
    st.markdown("### 📜 Historique Apify")
    
    history = get_apify_history()
    if history:
        for h in history:
            if st.button(h["label"], use_container_width=True, key=f"hist_{h['id']}"):
                st.session_state.selected_history = h
                st.rerun()
    else:
        st.markdown("*Aucune recherche récente*")

st.title("🎯 ANP Partners | Lead Machine")
st.markdown("Outil de prospection pour trouver des entreprises locales sur Google Maps")

if "results_df" not in st.session_state:
    st.session_state.results_df = None
if "filtered_df" not in st.session_state:
    st.session_state.filtered_df = None

if "selected_history" in st.session_state and st.session_state.selected_history:
    hist = st.session_state.selected_history
    with st.spinner(f"Chargement de: {hist['label']}..."):
        df = load_dataset_from_apify(hist["dataset_id"])
        if df is not None:
            st.session_state.results_df = df
            st.success(f"✅ {len(df)} résultats chargés depuis l'historique!")
        else:
            st.warning("⚠️ Impossible de charger ce dataset.")
    st.session_state.selected_history = None

if run_scraping:
    if not search_query:
        st.error("❌ Veuillez entrer une requête de recherche")
    else:
        api_token = os.getenv("APIFY_API_TOKEN")
        if not api_token:
            st.error("❌ APIFY_API_TOKEN non configuré. Veuillez ajouter votre token API Apify.")
        else:
            with st.spinner("🔄 Scraping en cours... Cela peut prendre quelques minutes."):
                try:
                    client = ApifyClient(api_token)
                    
                    run_input = {
                        "searchStringsArray": [search_query],
                        "maxCrawledPlacesPerSearch": max_results,
                        "language": "fr",
                    }
                    
                    st.write("📤 Envoi à Apify:", run_input)
                    
                    run = client.actor("compass/crawler-google-places").call(run_input=run_input)
                    
                    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
                    
                    st.write(f"🔍 Debug: Le robot a trouvé {len(items)} résultats bruts avant filtrage.")
                    
                    if items:
                        processed_items = []
                        for item in items:
                            processed_items.append({
                                "title": item.get("title"),
                                "address": item.get("address"),
                                "phone": item.get("phone") or item.get("phoneNumber"),
                                "website": item.get("website") or None,
                                "totalScore": item.get("totalScore"),
                                "reviewsCount": item.get("reviewsCount"),
                                "url": item.get("url"),
                            })
                        
                        df = pd.DataFrame(processed_items)
                        
                        if "website" in df.columns:
                            df["website"] = df["website"].replace("", None)
                        
                        st.session_state.results_df = df
                        st.success(f"✅ {len(df)} résultats trouvés!")
                    else:
                        st.warning("⚠️ Aucun résultat trouvé pour cette recherche.")
                        st.session_state.results_df = None
                        
                except Exception as e:
                    st.error(f"❌ Erreur lors du scraping: {str(e)}")
                    st.session_state.results_df = None

if st.session_state.results_df is not None:
    df = st.session_state.results_df.copy()
    
    st.header("🎯 Filtres Intelligents")
    
    col1, col2 = st.columns(2)
    
    with col1:
        filter_no_website = st.checkbox(
            "🎯 Cibles Prioritaires (Sans Site Web)",
            help="Afficher uniquement les entreprises sans site web"
        )
    
    with col2:
        filter_low_rating = st.checkbox(
            "📉 Cibles Réputation (Note < 4.5)",
            help="Afficher uniquement les entreprises avec une note inférieure à 4.5"
        )
    
    filtered_df = df.copy()
    
    if filter_no_website:
        if "website" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["website"].isna() | (filtered_df["website"] == "")]
    
    if filter_low_rating:
        if "totalScore" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["totalScore"] < 4.5]
    
    st.session_state.filtered_df = filtered_df
    
    st.subheader(f"📋 Résultats ({len(filtered_df)} prospects)")
    
    st.dataframe(
        filtered_df,
        use_container_width=True,
        column_config={
            "title": st.column_config.TextColumn("Nom", width="medium"),
            "address": st.column_config.TextColumn("Adresse", width="large"),
            "phone": st.column_config.TextColumn("Téléphone", width="small"),
            "website": st.column_config.LinkColumn("Site Web", width="medium"),
            "totalScore": st.column_config.NumberColumn("Note", format="%.1f", width="small"),
            "reviewsCount": st.column_config.NumberColumn("Avis", width="small"),
            "url": st.column_config.LinkColumn("Google Maps", width="medium"),
        }
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        csv = filtered_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Télécharger CSV",
            data=csv,
            file_name="prospects.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col2:
        st.markdown('<div class="sheets-btn">', unsafe_allow_html=True)
        if st.button("📤 Envoyer vers Google Sheets", type="primary", use_container_width=True, key="sheets_export"):
            with st.spinner("Envoi en cours..."):
                success, message = export_to_sheets(filtered_df, sheet_name)
                if success:
                    st.success(message)
                else:
                    st.error(message)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("👈 Configurez votre recherche dans la barre latérale et lancez le scraping.")
