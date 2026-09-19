import io
import json
import os
import secrets
import uuid
from datetime import datetime, timezone

import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

st.set_page_config(page_title="DAAC Photo Hub", page_icon="📷", layout="wide")
SCOPES = ["https://www.googleapis.com/auth/drive"]
INBOX_FOLDER_ID = "1HFbufjJ10tvxcA0ri8SP3cm0rIg5gRD2"
CATEGORY_FOLDERS = {
    "Open Houses": "1B7N_ypgTPFEInp-w_drbnxpub5hhVG1N",
    "Community Events": "1u-Obz83I88rFPtXuiuyEtzfcfzWsMbWH",
    "Environmental & Community Projects": "1yJl5Lwsj9EqLy1DC_g1F1r9XbPISbiDr",
    "Outreach & Partnerships": "1G2n-8p4cdOYSyJ8-x6dQWX_NY9PirYEn",
    "Social Media": "1HUSk5mwaDW4jAMp6sGYZbJ_2cd2y43mR",
    "Other / Needs Sorting": "1AjD8dOem0T601hbwMnnABuBMDzG5WNv5",
}
IMAGE_TYPES = ["jpg", "jpeg", "png", "webp", "heic", "heif"]


def secret_value(name):
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets[name]
    except (KeyError, FileNotFoundError):
        return None


@st.cache_resource
def drive_client():
    raw = secret_value("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("Google Drive is not connected yet.")
    info = json.loads(raw) if isinstance(raw, str) else dict(raw)
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def safe_filename(name):
    name = (name or "photo").replace("\\", "/").split("/")[-1].replace("\x00", "")
    return "".join(c for c in name if c.isalnum() or c in "._- ").strip() or "photo"


def file_bytes(file_id):
    request = drive_client().files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


@st.cache_data(ttl=180, show_spinner=False)
def cached_file_bytes(file_id, modified_time):
    del modified_time
    return file_bytes(file_id)


def list_folder(folder_id, limit=100):
    result = drive_client().files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id,name,mimeType,size,createdTime,modifiedTime,description,appProperties,parents)",
        orderBy="createdTime desc", pageSize=limit, supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return [item for item in result.get("files", []) if item.get("mimeType", "").startswith("image/")]


def pending_batches():
    batches = {}
    for item in list_folder(INBOX_FOLDER_ID, 500):
        props = item.get("appProperties") or {}
        batch_id = props.get("batch_id") or item["id"]
        batch = batches.setdefault(batch_id, {
            "id": batch_id,
            "event_name": props.get("event_name") or "Untitled upload",
            "suggested_category": props.get("suggested_category") or "Other / Needs Sorting",
            "uploader_name": props.get("uploader_name") or "DAAC team member",
            "notes": item.get("description") or "", "created_at": item.get("createdTime"), "files": [],
        })
        batch["files"].append(item)
    return sorted(batches.values(), key=lambda x: x.get("created_at") or "", reverse=True)


def upload_batch(files, category, event_name, uploader_name, notes):
    batch_id = uuid.uuid4().hex
    for uploaded in files:
        name = safe_filename(uploaded.name)
        media = MediaIoBaseUpload(io.BytesIO(uploaded.getvalue()), mimetype=uploaded.type or "application/octet-stream", resumable=True)
        drive_client().files().create(
            body={"name": name, "parents": [INBOX_FOLDER_ID], "description": notes,
                  "appProperties": {"batch_id": batch_id, "suggested_category": category[:124],
                                    "event_name": event_name[:124], "uploader_name": uploader_name[:124],
                                    "uploaded_via": "DAAC Photo Hub"},
                  "createdTime": datetime.now(timezone.utc).isoformat()},
            media_body=media, fields="id,name", supportsAllDrives=True,
        ).execute()
    cached_file_bytes.clear()


def approve_batch(batch, category, show_in_album):
    for item in batch["files"]:
        properties = dict(item.get("appProperties") or {})
        properties.update({"approved_category": category[:124], "album_visible": str(show_in_album).lower(),
                           "approved_at": datetime.now(timezone.utc).isoformat()[:124]})
        drive_client().files().update(
            fileId=item["id"], addParents=CATEGORY_FOLDERS[category],
            removeParents=",".join(item.get("parents") or [INBOX_FOLDER_ID]),
            body={"appProperties": properties}, fields="id,parents", supportsAllDrives=True,
        ).execute()
    cached_file_bytes.clear()


def reject_batch(batch):
    for item in batch["files"]:
        drive_client().files().update(fileId=item["id"], body={"trashed": True}, supportsAllDrives=True).execute()
    cached_file_bytes.clear()


@st.cache_data(ttl=300, show_spinner=False)
def album_files():
    photos = []
    for category, folder_id in CATEGORY_FOLDERS.items():
        for item in list_folder(folder_id, 40):
            if (item.get("appProperties") or {}).get("album_visible") == "true":
                item["category"] = category
                photos.append(item)
    return sorted(photos, key=lambda x: x.get("createdTime") or "", reverse=True)[:24]


def unlock():
    st.markdown("### Team access")
    st.caption("Enter the DAAC upload code or organizer code.")
    with st.form("access_form"):
        code = st.text_input("Access code", type="password")
        submitted = st.form_submit_button("Continue", use_container_width=True)
    if submitted:
        upload_code, admin_code = str(secret_value("UPLOAD_ACCESS_CODE") or ""), str(secret_value("ADMIN_ACCESS_CODE") or "")
        if admin_code and secrets.compare_digest(code, admin_code):
            st.session_state.role = "admin"; st.rerun()
        if upload_code and secrets.compare_digest(code, upload_code):
            st.session_state.role = "uploader"; st.rerun()
        st.error("That access code is not valid.")


def render_album():
    st.markdown("# Community in action.")
    st.write("Recent moments from DAAC events, programs, partnerships, and environmental work.")
    try:
        photos = album_files()
    except Exception as exc:
        st.info(f"The photo album will appear after Google Drive is connected. ({exc})"); return
    if not photos:
        st.info("Photos approved for the homepage album will appear here."); return
    columns = st.columns(3)
    for index, photo in enumerate(photos):
        try:
            columns[index % 3].image(cached_file_bytes(photo["id"], photo.get("modifiedTime", "")), caption=photo["category"], use_container_width=True)
        except Exception:
            pass


def render_upload():
    st.markdown("# Share photos with DAAC")
    st.write("Photos are saved permanently in Google Drive. An organizer confirms the final folder before they leave Pending Approval.")
    with st.form("upload_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        uploader = col1.text_input("Your name *")
        event_name = col2.text_input("Event or project name *")
        category = st.selectbox("Suggested category *", list(CATEGORY_FOLDERS))
        files = st.file_uploader("Photos *", type=IMAGE_TYPES, accept_multiple_files=True)
        notes = st.text_area("Notes (optional)")
        submitted = st.form_submit_button("Send for approval", use_container_width=True)
    if submitted:
        if not uploader.strip() or not event_name.strip() or not files:
            st.error("Add your name, the event or project name, and at least one photo."); return
        too_large = [item.name for item in files if item.size > 25 * 1024 * 1024]
        if too_large:
            st.error("These photos exceed 25 MB: " + ", ".join(too_large)); return
        try:
            with st.spinner("Saving photos permanently to Google Drive…"):
                upload_batch(files, category, event_name.strip(), uploader.strip(), notes.strip())
            st.success(f"Received! {len(files)} photo{'s are' if len(files) != 1 else ' is'} waiting for approval.")
        except Exception as exc:
            st.error(f"The upload could not be completed: {exc}")


def render_review():
    st.markdown("# Photos waiting for review")
    st.write("Confirm the destination, choose whether the photos appear in the album, and move them into their permanent folder.")
    try:
        batches = pending_batches()
    except Exception as exc:
        st.error(f"The pending folder could not be opened: {exc}"); return
    st.metric("Pending batches", len(batches))
    if not batches:
        st.success("You are all caught up."); return
    for batch in batches:
        with st.container(border=True):
            st.subheader(batch["event_name"])
            st.caption(f"{batch['uploader_name']} · {len(batch['files'])} photo{'s' if len(batch['files']) != 1 else ''}")
            if batch["notes"]: st.write(batch["notes"])
            preview_columns = st.columns(min(4, len(batch["files"])))
            for index, item in enumerate(batch["files"][:8]):
                try:
                    preview_columns[index % len(preview_columns)].image(cached_file_bytes(item["id"], item.get("modifiedTime", "")), caption=item["name"], use_container_width=True)
                except Exception:
                    preview_columns[index % len(preview_columns)].caption(item["name"])
            categories = list(CATEGORY_FOLDERS)
            default = categories.index(batch["suggested_category"]) if batch["suggested_category"] in categories else 5
            category = st.selectbox("Permanent Drive folder", categories, index=default, key=f"cat_{batch['id']}")
            show = st.checkbox("Show these photos in the homepage album", key=f"gallery_{batch['id']}")
            approve_col, reject_col = st.columns(2)
            if approve_col.button("Approve and move", key=f"approve_{batch['id']}", type="primary", use_container_width=True):
                try:
                    approve_batch(batch, category, show); album_files.clear(); st.rerun()
                except Exception as exc: st.error(f"Could not approve this batch: {exc}")
            if reject_col.button("Move to Drive trash", key=f"reject_{batch['id']}", use_container_width=True):
                try:
                    reject_batch(batch); st.rerun()
                except Exception as exc: st.error(f"Could not reject this batch: {exc}")


st.markdown("""<style>
[data-testid="stAppViewContainer"]{background:linear-gradient(180deg,#f5fbfb 0%,#fff 70%)}
.block-container{max-width:1120px;padding-top:2rem;padding-bottom:5rem}h1{color:#123844;letter-spacing:-.035em}h2,h3{color:#176d73}
[data-testid="stMetric"]{background:white;border:1px solid #cfe4e6;border-radius:16px;padding:16px}
[data-testid="stForm"],[data-testid="stVerticalBlockBorderWrapper"]{background:white;border-color:#cfe4e6!important;border-radius:20px!important}
.stButton>button,.stFormSubmitButton>button{border-radius:12px;font-weight:750}
</style>""", unsafe_allow_html=True)

if "role" not in st.session_state: st.session_state.role = None
with st.sidebar:
    st.markdown("## DAAC Photo Hub")
    page = st.radio("Go to", ["Album", "Upload"] + (["Review"] if st.session_state.role == "admin" else []), label_visibility="collapsed")
    if st.session_state.role:
        st.caption(f"Unlocked as {st.session_state.role}")
        if st.button("Lock app", use_container_width=True): st.session_state.role = None; st.rerun()

if page == "Album": render_album()
elif not st.session_state.role: unlock()
elif page == "Upload": render_upload()
elif page == "Review" and st.session_state.role == "admin": render_review()
