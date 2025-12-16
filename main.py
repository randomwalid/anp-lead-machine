import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime
from apify_client import ApifyClient
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="ANP Partners | Lead Machine",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS "BLINDÉ" (DESIGN) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    
    /* --- GLOBAL RESET --- */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #150d2e;
    }

    /* --- BACKGROUNDS --- */
    .stApp {
        background-color: #fff1e6 !important;
    }
    
    .main .block-container {
        background-color: #fff1e6 !important;
        padding-top: 2rem !important;
    }

    /* HEADER & TABS */
    header, header[data-testid="stHeader"] {
        background-color: #fff1e6 !important;
    }
    
    /* Onglets (Tabs) */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #fff1e6;
        border-bottom: 2px solid #efd9ce;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        font-size: 1.1rem;
        font-weight: 600;
        color: #150d2e;
    }
    .stTabs [aria-selected="true"] {
        color: #b79ced !important;
        border-bottom-color: #b79ced !important;
    }

    /* SIDEBAR */
    section[data-testid="stSidebar"] {
        background-color: #f8e8e7 !important;
        border-right: 1px solid #efd9ce;
    }
    section[data-testid="stSidebar"] > div {
        background-color: #f8e8e7 !important;
    }

    /* WIDGETS */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"], div[data-testid="stDataFrame"] {
        background-color: #ffffff !important;
        color: #150d2e !important;
        border: 1px solid #e0d2f8 !important;
        border-radius: 8px;
    }
    
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
    
    /* HIDE MENU */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
</style>
""", unsafe_allow_html=True)

# --- FONCTIONS UTILES ---

def get_google_creds():
    """Récupère les crédentials Google depuis les secrets"""
    try:
        creds_json = os.getenv("GOOGLE_CREDENTIALS")
        if not creds_json:
            return None, "❌ GOOGLE_CREDENTIALS non configuré."
        creds_dict = json.loads(creds_json)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return creds, "OK"
    except Exception as e:
        return None, str(e)

def load_data_from_sheets(sheet_name):
    """Lit les données du Google Sheet pour le CRM"""
    creds, msg = get_google_creds()
    if not creds:
        return None, msg
    
    try:
        gc = gspread.authorize(creds)
        spreadsheet = gc.open(sheet_name)
        sheet = spreadsheet.sheet1
        data = sheet.get_all_records() # Récupère tout sous forme de liste de dicos
        
        if not data:
            return pd.DataFrame(), "Vide"
            
        df = pd.DataFrame(data)
        return df, "OK"
    except gspread.SpreadsheetNotFound:
        return None, "⚠️ Fichier introuvable."
    except Exception as e:
        return None, f"Erreur: {str(e)}"

def export_to_sheets(dataframe, sheet_name):
    """Exporte (ajoute) les données vers Google Sheets"""
    creds, msg = get_google_creds()
    if not creds:
        return False, msg
    
    try:
        gc = gspread.authorize(creds)
        try:
            spreadsheet = gc.open(sheet_name)
        except gspread.SpreadsheetNotFound:
            return False, "⚠️ Impossible de trouver le fichier. Vérifiez le nom et le partage."
        
        sheet = spreadsheet.sheet1
        existing_data = sheet.get_all_values()
        
        if len(existing_data) == 0:
            headers = ["Nom", "Adresse", "Téléphone", "Site Web", "Note", "Avis", "Date Ajout", "Statut"]
            sheet.append_row(headers)
        
        # Ajout de la date et statut par défaut
        dataframe["Date Ajout"] = datetime.now().strftime("%d/%m/%Y")
        dataframe["Statut"] = "A Contacter" # Nouveau champ pour le CRM
        
        # Préparation des données (sélection des colonnes dans le bon ordre)
        export_data = []
        for _, row in dataframe.iterrows():
            row_data = [
                str(row.get("title", "") or ""),
                str(row.get("address", "") or ""),
                str(row.get("phone", "") or ""),
                str(row.get("website", "") or ""),
                str(row.get("totalScore", "") or ""),
                str(row.get("reviewsCount", "") or ""),
                str(row.get("Date Ajout", "")),
                str(row.get("Statut", ""))
            ]
            export_data.append(row_data)

        # Ajout en bloc (plus rapide)
        sheet.append_rows(export_data)
        
        return True, f"✅ {len(dataframe)} leads ajoutés à la base !"
    except Exception as e:
        return False, f"❌ Erreur: {str(e)}"

def get_apify_history():
    """Récupère l'historique Apify"""
    try:
        api_token = os.getenv("APIFY_API_TOKEN")
        if not api_token: return []
        client = ApifyClient(api_token)
        runs_response = client.runs().list(limit=5, desc=True) # Limité à 5 pour être propre
        items = runs_response.get("items", []) if isinstance(runs_response, dict) else []
        
        history = []
        for run in items:
            if run.get("status") == "SUCCEEDED":
                search_term = "Recherche"
                if run.get("input") and run["input"].get("searchStringsArray"):
                    search_term = run["input"]["searchStringsArray"][0]
                
                started_at = run.get("startedAt", "")[:10]
                history.append({
                    "id": run.get("id"),
                    "label": f"{search_term} ({started_at})",
                    "dataset_id": run.get("defaultDatasetId")
                })
        return history
    except:
        return []

def load_dataset_from_apify(dataset_id):
    """Charge un dataset Apify"""
    try:
        api_token = os.getenv("APIFY_API_TOKEN")
        client = ApifyClient(api_token)
        items = list(client.dataset(dataset_id).iterate_items())
        if items:
            df = pd.DataFrame(items)
            # Nettoyage basique
            cols_to_keep = ["title", "address", "phone", "phoneNumber", "website", "totalScore", "reviewsCount", "url"]
            df = df[[c for c in df.columns if c in cols_to_keep]]
            if "phoneNumber" in df.columns and "phone" not in df.columns:
                df.rename(columns={"phoneNumber": "phone"}, inplace=True)
            if "website" in df.columns:
                df["website"] = df["website"].replace("", None)
            return df
        return None
    except:
        return None

# --- SIDEBAR (PARAMÈTRES) ---
with st.sidebar:
    st.markdown("## 🎯 ANP Partners")
    st.markdown("### Lead Machine")
    st.markdown("---")
    
    st.info("💡 **Conseil:** Utilisez les onglets principaux pour naviguer entre la recherche et votre base de données.")
    
    st.markdown("### ⚙️ Configuration")
    sheet_name = st.text_input(
        "📁 Fichier Google Sheets",
        value="ANP_prospects_database",
        help="Le nom de votre fichier doit être exact."
    )

# --- CORPS PRINCIPAL ---
st.title("🎯 ANP Partners | Lead Machine")

# Création des onglets
tab_scraping, tab_crm = st.tabs(["🚀 Chasseur de Leads", "📁 Base de Données (CRM)"])

# --- ONGLET 1 : SCRAPING (L'ancien outil) ---
with tab_scraping:
    st.markdown("#### 🕵️‍♂️ Nouvelle Recherche")
    
    col_search, col_count = st.columns([3, 1])
    with col_search:
        search_query = st.text_input("🔍 Requête (ex: Plombier Lyon)", key="search_input")
    with col_count:
        max_results = st.number_input("Nombre Max", min_value=1, max_value=200, value=20, key="max_input")
    
    col_btn, col_hist = st.columns([1, 2])
    with col_btn:
        run_scraping = st.button("🚀 Lancer le Scraping", type="primary", use_container_width=True)
    
    # Historique rapide
    with col_hist:
        with st.expander("📜 Historique récent"):
            history = get_apify_history()
            if history:
                for h in history:
                    if st.button(h["label"], key=f"hist_{h['id']}"):
                        st.session_state.selected_history = h
                        st.rerun()
            else:
                st.write("Aucun historique.")

    # Logique de chargement (Historique ou Nouveau Scraping)
    if "results_df" not in st.session_state:
        st.session_state.results_df = None

    # 1. Chargement Historique
    if "selected_history" in st.session_state and st.session_state.selected_history:
        with st.spinner("Chargement de l'historique..."):
            df_hist = load_dataset_from_apify(st.session_state.selected_history["dataset_id"])
            if df_hist is not None:
                st.session_state.results_df = df_hist
                st.success(f"✅ Historique chargé : {len(df_hist)} leads")
            st.session_state.selected_history = None

    # 2. Lancement Scraping
    if run_scraping:
        if not search_query:
            st.error("❌ Indiquez une recherche.")
        else:
            api_token = os.getenv("APIFY_API_TOKEN")
            if not api_token:
                st.error("❌ Clé API manquante dans les secrets.")
            else:
                with st.spinner("🔄 Le robot travaille..."):
                    try:
                        client = ApifyClient(api_token)
                        run_input = {
                            "searchStringsArray": [search_query],
                            "maxCrawledPlacesPerSearch": max_results,
                            "language": "fr",
                        }
                        st.write(f"📤 Recherche lancée pour : {search_query} ({max_results} max)")
                        run = client.actor("compass/crawler-google-places").call(run_input=run_input)
                        dataset_items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
                        
                        if dataset_items:
                            # Transformation en DataFrame propre
                            processed = []
                            for item in dataset_items:
                                processed.append({
                                    "title": item.get("title"),
                                    "address": item.get("address"),
                                    "phone": item.get("phone") or item.get("phoneNumber"),
                                    "website": item.get("website"),
                                    "totalScore": item.get("totalScore"),
                                    "reviewsCount": item.get("reviewsCount"),
                                    "url": item.get("url")
                                })
                            st.session_state.results_df = pd.DataFrame(processed)
                            st.success(f"✅ {len(processed)} résultats trouvés !")
                        else:
                            st.warning("⚠️ Aucun résultat trouvé.")
                    except Exception as e:
                        st.error(f"Erreur: {str(e)}")

    # Affichage Résultats Scraping + Filtres
    if st.session_state.results_df is not None:
        df = st.session_state.results_df.copy()
        
        st.markdown("---")
        st.markdown("#### 🎯 Filtrer & Exporter")
        
        c1, c2 = st.columns(2)
        with c1:
            filter_no_website = st.checkbox("Sans Site Web uniquement")
        with c2:
            filter_low_rating = st.checkbox("Note < 4.5 uniquement")
            
        if filter_no_website and "website" in df.columns:
            df = df[df["website"].isna() | (df["website"] == "")]
        if filter_low_rating and "totalScore" in df.columns:
            df = df[df["totalScore"] < 4.5]
            
        st.dataframe(
            df,
            use_container_width=True,
            column_config={
                "website": st.column_config.LinkColumn("Site Web"),
                "url": st.column_config.LinkColumn("Maps")
            }
        )
        
        if st.button("📤 Ajouter ces Leads à ma Base de Données (Google Sheets)", type="primary"):
            with st.spinner("Export en cours..."):
                success, msg = export_to_sheets(df, sheet_name)
                if success:
                    st.success(msg)
                    st.balloons()
                else:
                    st.error(msg)

# --- ONGLET 2 : CRM (Le Dashboard) ---
with tab_crm:
    st.markdown("#### 📁 Ma Base de Données (Google Sheets)")
    
    col_refresh, col_kpi = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 Actualiser la vue"):
            st.rerun()
            
    # Chargement des données
    df_crm, msg_crm = load_data_from_sheets(sheet_name)
    
    if df_crm is None:
        st.error(msg_crm)
    elif df_crm.empty:
        st.info("Votre base de données est vide pour l'instant. Allez dans l'onglet 'Chasseur' pour en ajouter !")
    else:
        # Calculs KPI
        total_leads = len(df_crm)
        
        # Gestion des colonnes manquantes (au cas où)
        if "Note" not in df_crm.columns: df_crm["Note"] = 0
        
        # Nettoyage pour calcul moyenne
        df_crm["Note"] = pd.to_numeric(df_crm["Note"], errors='coerce').fillna(0)
        avg_score = df_crm["Note"].mean()

        # Affichage KPI
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Prospects", total_leads)
        k2.metric("Note Moyenne Base", f"{avg_score:.1f}/5")
        k3.metric("Dernier import", datetime.now().strftime("%H:%M"))
        
        st.markdown("---")
        
        # Filtre de recherche dans la base
        text_search = st.text_input("🔎 Chercher dans la base (Nom, Ville...)", placeholder="Ex: Avocat...")
        
        if text_search:
            # Filtre simple insensible à la casse
            mask = df_crm.astype(str).apply(lambda x: x.str.contains(text_search, case=False, na=False)).any(axis=1)
            df_display = df_crm[mask]
        else:
            df_display = df_crm

        # Tableau interactif (Lecture Seule améliorée)
        st.dataframe(
            df_display,
            use_container_width=True,
            height=600,
            column_config={
                "Site Web": st.column_config.LinkColumn("Site Web"),
                "Note": st.column_config.NumberColumn("Note", format="%.1f"),
                "Date Ajout": st.column_config.TextColumn("Date Import"),
                "Statut": st.column_config.SelectboxColumn(
                    "Statut (Info)",
                    options=["A Contacter", "Contacté", "RDV Pris", "Signé", "Pas intéressé"],
                    help="Pour modifier le statut, faites-le directement dans Google Sheets pour l'instant."
                )
            }
        )
        st.caption("ℹ️ Pour modifier les données (changer un statut, supprimer une ligne), ouvrez directement votre Google Sheet. Les modifications apparaîtront ici après 'Actualiser'.")
