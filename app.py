import base64
import os
import secrets

import requests
import streamlit as st

st.set_page_config(page_title="DAAC Photo Hub", page_icon="📷", layout="wide")

CATEGORIES = [
    "Open Houses",
    "Community Events",
    "Environmental & Community Projects",
    "Outreach & Partnerships",
    "Social Media",
    "Other / Needs Sorting",
]
IMAGE_TYPES = ["jpg", "jpeg", "png", "webp", "heic", "heif"]


def setting(name):
    return os.environ.get(name) or st.secrets.get(name)


def app_script(action, **payload):
    url, token = setting("APPS_SCRIPT_URL"), setting("APPS_SCRIPT_TOKEN")
    if not url or not token:
        raise RuntimeError("The free Google Drive connection has not been configured yet.")
    response = requests.post(url, json={"token": token, "action": action, **payload}, timeout=90)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Google Drive could not complete that request."))
    return data


def code_matches(value, setting_name):
    expected = str(setting(setting_name) or "")
    return bool(expected) and secrets.compare_digest(value or "", expected)


def decode_image(value):
    return base64.b64decode(value) if value else None


def unlock():
    st.markdown("### Team access")
    st.caption("Enter the DAAC upload code or organizer code.")
    with st.form("access_form"):
        code = st.text_input("Access code", type="password")
        submit = st.form_submit_button("Continue", use_container_width=True)
    if submit:
        if code_matches(code, "ADMIN_ACCESS_CODE"):
            st.session_state.role = "admin"
            st.rerun()
        if code_matches(code, "UPLOAD_ACCESS_CODE"):
            st.session_state.role = "uploader"
            st.rerun()
        st.error("That access code is not valid.")


def render_album():
    st.title("Community in action")
    st.write("Recent DAAC photos selected by an organizer.")
    try:
        photos = app_script("album").get("photos", [])
    except Exception as exc:
        st.info(str(exc))
        return
    if not photos:
        st.info("Photos approved for the album will appear here.")
        return
    columns = st.columns(3)
    for number, photo in enumerate(photos):
        image = decode_image(photo.get("thumbnail"))
        if image:
            columns[number % 3].image(image, caption=photo.get("category", ""), use_container_width=True)


def render_upload():
    st.title("Share photos with DAAC")
    st.write("Every upload goes directly into the permanent Google Drive Pending Approval folder. Nothing is stored anywhere else.")
    with st.form("upload_form", clear_on_submit=True):
        left, right = st.columns(2)
        uploader = left.text_input("Your name *")
        event = right.text_input("Event or project name *")
        category = st.selectbox("Suggested category *", CATEGORIES)
        photos = st.file_uploader("Photos *", type=IMAGE_TYPES, accept_multiple_files=True)
        notes = st.text_area("Notes (optional)")
        submit = st.form_submit_button("Send for approval", use_container_width=True)
    if not submit:
        return
    if not uploader.strip() or not event.strip() or not photos:
        st.error("Add your name, the event or project name, and at least one photo.")
        return
    too_large = [photo.name for photo in photos if photo.size > 15 * 1024 * 1024]
    if too_large:
        st.error("These files are larger than 15 MB: " + ", ".join(too_large))
        return
    files = [{
        "name": photo.name,
        "mimeType": photo.type or "image/jpeg",
        "base64": base64.b64encode(photo.getvalue()).decode("ascii"),
    } for photo in photos]
    try:
        with st.spinner("Saving photos to Google Drive…"):
            app_script("upload", uploader=uploader.strip(), eventName=event.strip(),
                       category=category, notes=notes.strip(), files=files)
        st.success(f"Received! {len(files)} photo{'s are' if len(files) != 1 else ' is'} waiting for approval.")
    except Exception as exc:
        st.error(f"Upload could not be completed: {exc}")


def render_review():
    st.title("Photos waiting for review")
    st.write("Choose the permanent Google Drive folder, then approve or reject each batch.")
    try:
        batches = app_script("pending").get("batches", [])
    except Exception as exc:
        st.error(str(exc))
        return
    st.metric("Pending batches", len(batches))
    if not batches:
        st.success("You are all caught up.")
        return
    for batch in batches:
        with st.container(border=True):
            st.subheader(batch.get("eventName") or "Untitled upload")
            st.caption(f"{batch.get('uploader') or 'DAAC team member'} · {len(batch['files'])} photo(s)")
            if batch.get("notes"):
                st.write(batch["notes"])
            preview_columns = st.columns(min(4, len(batch["files"])))
            for index, photo in enumerate(batch["files"]):
                thumbnail = decode_image(photo.get("thumbnail"))
                if thumbnail:
                    preview_columns[index % len(preview_columns)].image(thumbnail, caption=photo["name"], use_container_width=True)
            default = CATEGORIES.index(batch["suggestedCategory"]) if batch.get("suggestedCategory") in CATEGORIES else len(CATEGORIES) - 1
            category = st.selectbox("Permanent Drive folder", CATEGORIES, index=default, key=f"cat_{batch['id']}")
            album = st.checkbox("Show these photos in the homepage album", key=f"album_{batch['id']}")
            approve, reject = st.columns(2)
            if approve.button("Approve and move", type="primary", use_container_width=True, key=f"approve_{batch['id']}"):
                try:
                    app_script("approve", batchId=batch["id"], category=category, albumVisible=album)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
            if reject.button("Move to Drive trash", use_container_width=True, key=f"reject_{batch['id']}"):
                try:
                    app_script("reject", batchId=batch["id"])
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


st.markdown("""
<style>
[data-testid="stAppViewContainer"]{background:linear-gradient(180deg,#f4fbfb 0%,#ffffff 70%)}
.block-container{max-width:1120px;padding-top:2rem;padding-bottom:5rem}
h1,h2,h3{color:#176d73}.stButton>button,.stFormSubmitButton>button{border-radius:12px;font-weight:750}
</style>
""", unsafe_allow_html=True)

if "role" not in st.session_state:
    st.session_state.role = None

with st.sidebar:
    st.header("DAAC Photo Hub")
    pages = ["Album", "Upload"] + (["Review"] if st.session_state.role == "admin" else [])
    page = st.radio("Go to", pages, label_visibility="collapsed")
    if st.session_state.role:
        st.caption(f"Unlocked as {st.session_state.role}")
        if st.button("Lock app", use_container_width=True):
            st.session_state.role = None
            st.rerun()

if page == "Album":
    render_album()
elif not st.session_state.role:
    unlock()
elif page == "Upload":
    render_upload()
else:
    render_review()
