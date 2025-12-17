import streamlit as st
import pandas as pd
import os
import json
import time
from datetime import datetime
from apify_client import ApifyClient
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import google.generativeai as genai # On utilise Google au lieu d'OpenAI

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="ANP Partners | Lead Machine",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS (DESIGN) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #150d2e; }
    .stApp { background-color: #fff1e6 !important; }
    .main .block-container { background-color: #fff1e6 !important; padding-top: 2rem !important; }
    header, header[data-testid="stHeader"] { background-color: #fff1e6 !important; }
    .stTabs [data-baseweb="tab-list"] { background-color: #fff1e6; border-bottom: 2px solid #efd9ce; }
    .stTabs [data-baseweb="tab"] { height: 50px; font-size: 1.1rem; font-weight: 600; color: #150d2e; }
    .stTabs [aria-selected="true"] { color: #b79ced !important; border-bottom-color: #b79ced !important; }
    section[data-testid="stSidebar"] { background-color: #f8e8e7 !important; border-right: 1px solid #efd9ce; }
    section[data-testid="stSidebar"] > div { background-color: #f8e8e7 !important; }
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"], div[data-testid="stDataFrame"] { background-color: #ffffff !important; color: #150d2e !important; border: 1px solid #e0d2f8 !important; border-radius: 8px; }
    div.stButton > button { background-color: #b79ced !important; color: #150d2e !important; border: none; border-radius: 8px; font-weight: 600; }
    div.stButton > button:hover { opacity: 0.9; border: 1px solid #150d2e !important; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} .stDeployButton {display:none;}
</style>
""", unsafe_allow_html=True)

# --- FONCTIONS ---

def get_google_creds():
    try:
        creds_json = os.getenv("GOOGLE_CREDENTIALS")
        if not creds_json: return None, "❌ GOOGLE_CREDENTIALS manquant."
        creds_dict = json.loads(creds_json)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return creds, "OK"
    except Exception as e: return None, str(e)

def load_data_from_sheets(sheet_name):
    creds, msg = get_google_creds()
    if not creds: return None, msg
    try:
        gc = gspread.authorize(creds)
        sheet = gc.open(sheet_name).sheet1
        data = sheet.get_all_records()
        if not data: return pd.DataFrame(), "Vide"
        return pd.DataFrame(data), "OK"
    except gspread.SpreadsheetNotFound: return None, "⚠️ Fichier introuvable."
    except Exception as e: return None, f"Erreur: {str(e)}"

def export_to_sheets(dataframe, sheet_name):
    creds, msg = get_google_creds()
    if not creds: return False, msg
    try:
        gc = gspread.authorize(creds)
        try: spreadsheet = gc.open(sheet_name)
        except: return False, "⚠️ Fichier introuvable."
        
        sheet = spreadsheet.sheet1
        existing_data = sheet.get_all_values()
        
        # En-têtes mis à jour
        headers = ["Nom", "Adresse", "Téléphone", "Email", "Site Web", "Note", "Avis", "Date Ajout", "Statut", "Brouillon IA"]
        
        if len(existing_data) == 0:
            sheet.append_row(headers)
        
        dataframe["Date Ajout"] = datetime.now().strftime("%d/%m/%Y")
        if "Statut" not in dataframe.columns: dataframe["Statut"] = "A Contacter"
        if "Brouillon IA" not in dataframe.columns: dataframe["Brouillon IA"] = ""
        
        export_data = []
        for _, row in dataframe.iterrows():
            row_data = [
                str(row.get("title", "") or ""),
                str(row.get("address", "") or ""),
                str(row.get("phone", "") or ""),
                str(row.get("email", "") or ""),  # Nouvelle colonne Email
                str(row.get("website", "") or ""),
                str(row.get("totalScore", "") or ""),
                str(row.get("reviewsCount", "") or ""),
                str(row.get("Date Ajout", "")),
                str(row.get("Statut", "")),
                str(row.get("Brouillon IA", ""))
            ]
            export_data.append(row_data)

        sheet.append_rows(export_data)
        return True, f"✅ {len(dataframe)} leads ajoutés !"
    except Exception as e: return False, f"❌ Erreur: {str(e)}"

def generate_ai_email(row, api_key):
    """Génère un email personnalisé avec Google Gemini"""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        nom = row.get("Nom") or row.get("title") or "l'équipe"
        note = str(row.get("Note") or row.get("totalScore") or "0")
        site = row.get("Site Web") or row.get("website") or ""
        
        contexte = f"Prospect: {nom}. Note Google: {note}/5. "
        if not site: contexte += "N'a pas de site web. "
        else: contexte += f"A un site web ({site}). "
        
        prompt = f"""
        Tu es un expert en prospection commerciale. Rédige un email froid (cold email) très court (max 60 mots) et percutant pour ce prospect.
        Ton objectif : Proposer un RDV pour améliorer leur visibilité en ligne.
        Infos prospect : {contexte}
        Si la note est basse, mentionne subtilement les avis. Si pas de site, insiste sur le manque de visibilité.
        Ne mets pas d'objet, juste le corps du mail. Ton : Professionnel mais direct.
        """
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Erreur IA: {str(e)}"

def load_dataset_from_apify(dataset_id):
    try:
        api_token = os.getenv("APIFY_API_TOKEN")
        client = ApifyClient(api_token)
        items = list(client.dataset(dataset_id).iterate_items())
        if items:
            processed = []
            for item in items:
                # TENTATIVE DE RECUPERATION D'EMAIL (Priorité aux scrapers maps)
                email = item.get("email")
                # Certains scrapers mettent les emails dans une liste "emails" ou "contact"
                if not email and "emails" in item and isinstance(item["emails"], list) and len(item["emails"]) > 0:
                    email = item["emails"][0]
                
                processed.append({
                    "title": item.get("title"),
                    "address": item.get("address"),
                    "phone": item.get("phone") or item.get("phoneNumber"),
                    "email": email, # Ajout Email
                    "website": item.get("website"),
                    "totalScore": item.get("totalScore"),
                    "reviewsCount": item.get("reviewsCount"),
                    "url": item.get("url")
                })
            df = pd.DataFrame(processed)
            if "website" in df.columns: df["website"] = df["website"].replace("", None)
            return df
        return None
    except: return None

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("## 🎯 ANP Partners")
    st.markdown("### Lead Machine & IA")
    sheet_name = st.text_input("📁 Fichier Sheets", value="ANP_prospects_database")
    
    st.markdown("---")
    st.markdown("### 🧠 Configuration IA")
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        st.warning("Clé Google API manquante dans les secrets.")
    else:
        st.success("Gemini Connecté 🟢")

# --- MAIN ---
st.title("🎯 ANP Partners | Lead Machine")
tab_scraping, tab_crm = st.tabs(["🚀 Chasseur", "🤖 CRM & IA"])

# ONGLET 1 : CHASSEUR
with tab_scraping:
    c1, c2 = st.columns([3, 1])
    search = c1.text_input("🔍 Recherche (ex: Plombier Lyon)")
    limit = c2.number_input("Max", 1, 100, 20)
    
    if st.button("🚀 Lancer", type="primary"):
        with st.spinner("Le robot chasse..."):
            try:
                client = ApifyClient(os.getenv("APIFY_API_TOKEN"))
                # On force le scraper à chercher plus d'infos (mails)
                run_input = {
                    "searchStringsArray": [search],
                    "maxCrawledPlacesPerSearch": limit,
                    "language": "fr",
                    "maxCrawledPlaces": limit 
                }
                run = client.actor("compass/crawler-google-places").call(run_input=run_input)
                st.session_state.results_df = load_dataset_from_apify(run["defaultDatasetId"])
                st.success("Terminé !")
            except Exception as e: st.error(f"Erreur: {e}")

    # Affichage Résultats
    if "results_df" in st.session_state and st.session_state.results_df is not None:
        df = st.session_state.results_df
        st.dataframe(df, use_container_width=True)
        if st.button("📤 Envoyer vers CRM (Sheets)"):
            ok, msg = export_to_sheets(df, sheet_name)
            if ok: st.success(msg)
            else: st.error(msg)

# ONGLET 2 : CRM & IA
with tab_crm:
    if st.button("🔄 Actualiser"): st.rerun()
    
    df_crm, msg = load_data_from_sheets(sheet_name)
    if df_crm is None or df_crm.empty:
        st.info("Base vide ou inaccessible.")
    else:
        st.markdown(f"**Total Prospects:** {len(df_crm)}")
        
        # --- ZONE IA ---
        st.markdown("---")
        st.subheader("✨ Assistant de Rédaction IA (Gemini)")
        
        # On vérifie si la colonne "Brouillon IA" est vide pour certains
        if "Brouillon IA" not in df_crm.columns:
            df_crm["Brouillon IA"] = ""
            
        prospects_sans_mail = df_crm[df_crm["Brouillon IA"] == ""]
        nb_to_generate = len(prospects_sans_mail)
        
        c_gen1, c_gen2 = st.columns([3, 1])
        c_gen1.info(f"Il y a **{nb_to_generate}** prospects sans email rédigé.")
        
        if c_gen2.button("✨ Rédiger les Emails", disabled=(nb_to_generate==0)):
            if not google_api_key:
                st.error("Configurez la clé GOOGLE_API_KEY dans les secrets !")
            else:
                progress_bar = st.progress(0)
                creds, _ = get_google_creds()
                gc = gspread.authorize(creds)
                sheet = gc.open(sheet_name).sheet1
                
                all_records = sheet.get_all_records()
                
                for i, row in enumerate(all_records):
                    current_draft = row.get("Brouillon IA", "")
                    if not current_draft:
                        # Génération avec Gemini
                        draft = generate_ai_email(row, google_api_key)
                        
                        # Mise à jour Google Sheets (Colonne 10 = Brouillon IA)
                        try:
                            sheet.update_cell(i + 2, 10, draft)
                        except:
                            pass
                            
                    progress_bar.progress((i + 1) / len(all_records))
                
                st.success("✅ Tous les emails ont été rédigés par Gemini !")
                time.sleep(1)
                st.rerun()

        st.dataframe(df_crm, use_container_width=True, height=500)
