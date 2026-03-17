import os
from typing import Dict, List

import streamlit as st

import data
from config import (
    batch_config,
    coi_config,
    coi_deepseek_config,
    deepseek_config,
    sequential_config,
)
from main import get_provider
from translator import TranslatorCore


CONFIG_OPTIONS: Dict[str, dict] = {
    "LOTM - Gemini Sequential": sequential_config,
    "LOTM - Gemini Batch Config (run single chapter in UI)": batch_config,
    "LOTM - DeepSeek": deepseek_config,
    "COI - Gemini": coi_config,
    "COI - DeepSeek": coi_deepseek_config,
}


@st.cache_data(show_spinner=False)
def load_chapters_cached(pickle_file: str) -> List[dict]:
    return data.load_chapters(pickle_file)


def build_translator(config_name: str) -> TranslatorCore:
    cfg = dict(CONFIG_OPTIONS[config_name])
    provider = get_provider(cfg)
    return TranslatorCore(cfg, provider)


def get_output_path(translator: TranslatorCore, chapter_id: int) -> str:
    return os.path.join(translator.output_dir, f"Chapter_{chapter_id}.txt")


st.set_page_config(page_title="Novel Translator", layout="wide")
st.title("Chapter Translator (Stream Mode)")
st.caption("Click a chapter, then stream translation output in real time.")

config_name = st.selectbox("Config", list(CONFIG_OPTIONS.keys()), index=4)
translator = build_translator(config_name)

pickle_file = translator.pickle_file
chapters: List[dict] = []

try:
    chapters = load_chapters_cached(pickle_file)
except Exception as exc:
    st.error(f"Cannot load chapters from {pickle_file}: {exc}")
    st.stop()

if not chapters:
    st.warning("No chapters found.")
    st.stop()

chapter_map = {int(ch["chapter_id"]): ch for ch in chapters}
chapter_ids = sorted(chapter_map.keys())

if "selected_chapter_id" not in st.session_state:
    st.session_state.selected_chapter_id = chapter_ids[0]

left_col, right_col = st.columns([1, 2])

with left_col:
    st.subheader("Choose Chapter")
    search_text = st.text_input("Filter by title", "")
    max_show = st.slider("Chapters to show", min_value=10, max_value=200, value=40, step=10)

    filtered = chapters
    if search_text.strip():
        keyword = search_text.lower().strip()
        filtered = [ch for ch in chapters if keyword in str(ch.get("title", "")).lower()]

    for chapter in filtered[:max_show]:
        c_id = int(chapter["chapter_id"])
        title = str(chapter.get("title", ""))
        if st.button(f"Chapter {c_id}: {title}", use_container_width=True, key=f"pick-{c_id}"):
            st.session_state.selected_chapter_id = c_id

with right_col:
    selected_id = int(st.session_state.selected_chapter_id)
    selected = chapter_map[selected_id]
    selected_title = str(selected.get("title", ""))
    source_text = str(selected.get("text", ""))
    output_path = get_output_path(translator, selected_id)

    st.subheader(f"Chapter {selected_id}: {selected_title}")
    st.write(f"Source length: {len(source_text):,} chars")

    if os.path.exists(output_path):
        st.success(f"Already translated: {output_path}")
        with open(output_path, "r", encoding="utf-8") as f:
            st.text_area("Saved translation", f.read(), height=300)
    else:
        st.info("No translation file found yet.")

    with st.expander("Source text", expanded=False):
        st.text_area("Original", source_text, height=240)

    translate_clicked = st.button("Translate This Chapter (Stream)", type="primary")
    if translate_clicked:
        stream_box = st.empty()
        status = st.empty()

        raw_chunks: List[str] = []
        status.info("Streaming translation...")

        try:
            for chunk in translator.translate_chapter_stream(selected):
                raw_chunks.append(chunk)
                stream_box.markdown("".join(raw_chunks))

            translation_raw = "".join(raw_chunks)
            saved_path = translator.process_and_save_translation(selected_id, translation_raw)
            status.success(f"Done. Saved to: {saved_path}")
        except Exception as exc:
            status.error(f"Translation failed: {exc}")
