import streamlit as st
import os
import glob
import random
import pandas as pd
import time
import base64
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(
    page_title="展示物評価アプリ",
    layout="wide"
)

st.markdown(
    """
    <style>
    .main {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .block-container {
        max-width: 1400px;
        padding-top: 2rem;
    }
    h1 {
        font-size: 2.5rem !important;
        font-weight: 700 !important;
        margin-bottom: 1rem !important;
    }
    h2, h3 {
        margin-top: 0.5rem !important;
    }
    .stButton > button {
        width: 100%;
        height: 3rem;
        font-size: 1.1rem;
        border-radius: 12px;
    }
    .stTextArea textarea {
        border-radius: 12px;
    }
    .custom-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 16px;
        margin-bottom: 1rem;
        border: 1px solid #e5e7eb;
    }
    .evaluation-label {
        font-weight: bold;
        margin-top: 1rem;
        margin-bottom: 0.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

BASE_DIR = "Image"
MAX_OBSERVATION_IMAGES = 100
OBSERVATION_NUM_COLS = 6
OBSERVATION_SECONDS = 120

parts_options = {
    "こけし": ["頭部", "胴体"],
    "太鼓": ["胴", "面"],
    "仮面": ["目", "鼻", "口"]
}

score_map = {
    "🔴 典型的": -2,
    "🔴 やや典型的": -1,
    "⚫ どちらとも言い難い": 0,
    "🟡 やや非典型的": 1,
    "🟡 非典型的": 2
}
score_options = list(score_map.keys())

def get_image_base64(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
        ext = os.path.splitext(path)[1][1:].lower()
        if ext in ["jpg", "jpeg"]:
            mime = "image/jpeg"
        elif ext == "png":
            mime = "image/png"
        elif ext == "webp":
            mime = "image/webp"
        else:
            mime = "image/jpeg"
        b64 = base64.b64encode(data).decode()
        return f"data:{mime};base64,{b64}"
    except:
        return ""

@st.cache_data
def get_exhibit_structure(base_dir):
    structure = {}
    if not os.path.exists(base_dir):
        return structure
    exhibit_types = sorted([
        d for d in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, d))
    ])
    for exhibit_type in exhibit_types:
        structure[exhibit_type] = {
            "all": [],
            "regions": {}
        }
        type_path = os.path.join(base_dir, exhibit_type)
        folders = sorted([
            d for d in os.listdir(type_path)
            if os.path.isdir(os.path.join(type_path, d))
        ])
        for folder in folders:
            folder_path = os.path.join(type_path, folder)
            images = glob.glob(os.path.join(folder_path, "*"))
            images = [
                img for img in images
                if img.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
            images = sorted(images)
            if folder == "all":
                structure[exhibit_type]["all"] = images
            else:
                structure[exhibit_type]["regions"][folder] = images
    return structure

def save_to_gsheet(df):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    secret_info = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(
        secret_info,
        scopes=scopes)
    
    gc = gspread.authorize(credentials)
    spreadsheet = gc.open("BESC_Evaluation")
    worksheet = spreadsheet.sheet1
    existing_values = worksheet.get_all_values()
    if len(existing_values) == 0:
        worksheet.append_row(list(df.columns))
    rows = df.fillna("").astype(str).values.tolist()
    next_row = len(worksheet.get_all_values()) + 1
    cell_range = f"A{next_row}"
    worksheet.update(cell_range, rows)

data = get_exhibit_structure(BASE_DIR)
if not data:
    st.error("画像データが見つかりません")
    st.stop()

category_list = list(data.keys())

if "step" not in st.session_state:
    st.session_state.step = "observation"
if "category_index" not in st.session_state:
    st.session_state.category_index = 0
if "region_index" not in st.session_state:
    st.session_state.region_index = 0
if "eval_index" not in st.session_state:
    st.session_state.eval_index = 0
if "answers" not in st.session_state:
    st.session_state.answers = []
if "name" not in st.session_state:
    st.session_state.name = ""
if "saved" not in st.session_state:
    st.session_state.saved = False
if "observation_start_time" not in st.session_state:
    st.session_state.observation_start_time = None

if st.session_state.name == "":
    st.title("評価者情報")
    st.markdown(
        """
        <div class="custom-card">
        <h3>評価にご協力いただき、ありがとうございます。</h3>
        <p>これから展示物画像についての評価を行っていただきます。</p>
        <p>評価中にブラウザをリロードすると、最初からやり直しになる場合がありますので、ご注意ください。</p>
        <p>評価中に何か気になることがあれば、いつでも木下までご連絡ください。</p>
        <hr>
        評価開始前にお名前を入力してください。
        </div>
        """,
        unsafe_allow_html=True
    )
    participant_input = st.text_input("お名前", placeholder="例: 木下")
    if st.button("開始"):
        if participant_input.strip() == "":
            st.warning("名前を入力してください")
        else:
            st.session_state.name = participant_input.strip()
            st.rerun()
    st.stop()

current_type = category_list[st.session_state.category_index]
region_names = list(data[current_type]["regions"].keys())
current_region = region_names[st.session_state.region_index]
all_images = data[current_type]["regions"][current_region]

all_region_count = sum(len(data[c]["regions"]) for c in category_list)
completed_region_count = 0
for i in range(st.session_state.category_index):
    completed_region_count += len(data[category_list[i]]["regions"])
completed_region_count += st.session_state.region_index

progress_value = completed_region_count / all_region_count
st.progress(progress_value)
st.caption(f"進捗: {completed_region_count + 1} / {all_region_count}")

if "obs_type" not in st.session_state or st.session_state.obs_type != current_type:
    obs_images = data[current_type]["all"]
    rng = random.Random(f"fixed_seed_{current_type}")
    selected_images = rng.sample(obs_images, min(len(obs_images), MAX_OBSERVATION_IMAGES))
    rng.shuffle(selected_images)
    st.session_state.selected_obs_images = selected_images
    st.session_state.obs_type = current_type

if st.session_state.step == "observation":
    if st.session_state.observation_start_time is None:
        st.session_state.observation_start_time = datetime.now()
    st.title("全体観察フェーズ")
    st.markdown(
        f"""
        <div class="custom-card">
        <h3>これはカテゴリ: {current_type} の画像です。</h3>
        <p>画像を観察し、以下の3つの質問について、2分ほどの時間を使って1～3を繰り返し考えてください。</p>
        <p><b>Q1. このカテゴリの展示物には、どのような特徴や「らしさ」がありますか？</b></p>
        <p><b>Q2. 展示物のどの部分から、そう考えましたか？</b></p>
        <p><b>Q3. ほかにも気づくことや、比べてみたい点はありますか？</b></p>
        <p>2分が経過したら、観察終了・評価へ進むボタンを押して、評価に進んでください。</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    elapsed_time = (datetime.now() - st.session_state.observation_start_time).total_seconds()
    remaining_time = max(0, OBSERVATION_SECONDS - int(elapsed_time))
    minutes = remaining_time // 60
    seconds = remaining_time % 60
    st.info(f"観察時間: 残り {minutes:02d}:{seconds:02d}")

    images = st.session_state.selected_obs_images
    for i in range(0, len(images), OBSERVATION_NUM_COLS):
        cols = st.columns(OBSERVATION_NUM_COLS)
        for j in range(OBSERVATION_NUM_COLS):
            idx = i + j
            if idx < len(images):
                with cols[j]:
                    img_b64 = get_image_base64(images[idx])
                    if img_b64:
                        html_code = f"""
                        <img src="{img_b64}" style="width:100%; height:130px; object-fit:contain; background-color:#f1f3f5; border-radius:8px; margin-bottom:6px;">
                        """
                        st.markdown(html_code, unsafe_allow_html=True)
    st.divider()
    button_disabled = remaining_time > 0
    if st.button("観察終了・評価へ進む", disabled=button_disabled):
        st.session_state.observation_start_time = None
        st.session_state.step = "evaluation"
        st.rerun()
    if remaining_time > 0:
        time.sleep(1)
        st.rerun()

elif st.session_state.step == "evaluation":
    st.title("地域展示物評価")
    st.markdown(
        f"""
        <div class="custom-card">
        <h3>{current_type} / {current_region}</h3>
        <p>各展示物について典型性を評価してください。</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    current_image = all_images[st.session_state.eval_index]
    col1, col2 = st.columns([1, 1])
    with col1:
        main_img_b64 = get_image_base64(current_image)
        if main_img_b64:
            main_html = f"""
            <img src="{main_img_b64}" style="width:100%; height:auto; max-height:650px; object-fit:contain; display:block; border-radius:8px; margin-bottom:1rem;">
            """
            st.markdown(main_html, unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="custom-card">
            <b>画像番号:</b> {st.session_state.eval_index + 1} / {len(all_images)}
            </div>
            """,
            unsafe_allow_html=True
        )
    with col2:
        with st.form(f"eval_form_{st.session_state.category_index}_{st.session_state.region_index}_{st.session_state.eval_index}"):
            st.markdown('<p class="evaluation-label">Q1. 全体として外観がどの程度典型的であるか</p>', unsafe_allow_html=True)
            overall_selected = st.select_slider(
                "全体評価",
                options=score_options,
                value=score_options[2],
                label_visibility="collapsed"
            )
            overall_score = score_map[overall_selected]
            
            parts = parts_options.get(current_type, [])
            part_scores = {}
            
            for idx, part in enumerate(parts):
                st.markdown(f'<p class="evaluation-label">Q{idx+2}. {part}における外観がどの程度典型的であるか</p>', unsafe_allow_html=True)
                part_selected = st.select_slider(
                    f"{part}評価",
                    options=score_options,
                    value=score_options[2],
                    key=f"{part}_{st.session_state.category_index}_{st.session_state.region_index}_{st.session_state.eval_index}",
                    label_visibility="collapsed"
                )
                part_scores[part] = score_map[part_selected]
                
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("評価を保存して次へ")

    if submitted:
        answer_data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "name": st.session_state.name,
            "phase": "evaluation",
            "type": current_type,
            "region": current_region,
            "image_path": os.path.basename(current_image),
            "overall_score": overall_score
        }
        for part_name, value in part_scores.items():
            answer_data[f"part_{part_name}"] = value
        st.session_state.answers.append(answer_data)
        if st.session_state.eval_index < len(all_images) - 1:
            st.session_state.eval_index += 1
        else:
            st.session_state.eval_index = 0
            if st.session_state.region_index < len(region_names) - 1:
                st.session_state.region_index += 1
            else:
                st.session_state.region_index = 0
                if st.session_state.category_index < len(category_list) - 1:
                    st.session_state.category_index += 1
                    st.session_state.step = "observation"
                else:
                    st.session_state.step = "finish"
        st.rerun()

elif st.session_state.step == "finish":
    st.title("評価完了")
    st.success("すべての評価が終了しました。\n\nブラウザはこのまま閉じていただいて問題ありません。\n\nご協力いただき、ありがとうございました。")
    df = pd.DataFrame(st.session_state.answers)
    if not st.session_state.saved:
        try:
            save_to_gsheet(df)
            st.session_state.saved = True
            st.success("Google Sheetsへ保存しました")
        except Exception as e:
            st.error(f"Google Sheets保存エラー: {e}")
