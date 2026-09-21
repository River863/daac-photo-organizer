import base64
import os
import secrets
import requests
import streamlit as st

st.set_page_config(page_title="DAAC Photo Hub", page_icon="📷", layout="wide")
CATEGORIES = ["Open Houses", "Community Events", "Environmental & Community Projects", "Outreach & Partnerships", "Social Media", "Other / Needs Sorting"]
IMAGE_TYPES = ["jpg", "jpeg", "png", "webp", "heic", "heif"]

def setting(name): return os.environ.get(name) or st.secrets.get(name)

def app_script(action, **payload):
    url, token = setting("APPS_SCRIPT_URL"), setting("APPS_SCRIPT_TOKEN")
    if not url or not token: raise RuntimeError("The Google Drive connection has not been configured yet.")
    response = requests.post(url, json={"token": token, "action": action, **payload}, timeout=90)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"): raise RuntimeError(data.get("error", "Google Drive could not complete that request."))
    return data

def matches(value, name):
    expected = str(setting(name) or "")
    return bool(expected) and secrets.compare_digest(value or "", expected)

def image_bytes(photo): return base64.b64decode(photo["thumbnail"]) if photo.get("thumbnail") else None

def unlock():
    st.markdown("### Team access")
    with st.form("access_form"):
        code = st.text_input("Access code", type="password")
        submit = st.form_submit_button("Continue", use_container_width=True)
    if submit:
        if matches(code, "ADMIN_ACCESS_CODE"):
            st.session_state.role = "admin"; st.rerun()
        if matches(code, "UPLOAD_ACCESS_CODE"):
            st.session_state.role = "uploader"; st.rerun()
        st.error("That access code is not valid.")

def go_upload():
    st.session_state.page = "Upload"


def render_album():
    st.title("DAAC in the community")
    st.caption("A living record of DAAC’s events, projects, and partnerships.")
    st.button("📷  Upload photos to DAAC", type="primary", use_container_width=True, on_click=go_upload)
    try: gallery = app_script("gallery")
    except Exception as exc:
        st.error(str(exc)); return
    featured = [p for p in gallery.get("featured", []) if p.get("thumbnail")]
    st.markdown("## Latest from DAAC")
    if featured:
        cards = "".join("<a href='{0}' target='_blank'><figure><img src='data:image/jpeg;base64,{1}'><figcaption>Open / download: {2}</figcaption></figure></a>".format(p.get("url", "https://drive.google.com/file/d/{}/view".format(p["id"])), p["thumbnail"], p.get("albumName", "DAAC")) for p in featured)
        st.markdown(f"<div class='photo-strip'><div class='photo-track'>{cards}{cards}</div></div>", unsafe_allow_html=True)
    else: st.info("Photos will appear here once they are added to a DAAC event album.")
    st.markdown("## Explore photo albums")
    albums = gallery.get("albums", [])
    if not albums: st.info("No photo albums have been added yet.")
    for album in albums:
        with st.expander(f"{album['name']}  ·  {album['count']} photos"):
            st.caption(album.get("category", ""))
            
            if album.get("url"):
                st.link_button("Open this full album and download photos", album["url"], use_container_width=True)
            photos = [p for p in album.get("photos", []) if p.get("thumbnail")]
            if not photos: st.caption("These photos do not have browser previews yet.")
            else:
                columns = st.columns(min(4, len(photos)))
                for i, photo in enumerate(photos):
                    column = columns[i % len(columns)]
                    column.image(image_bytes(photo), use_container_width=True)
                    column.link_button("Open / download full photo", photo.get("url", "https://drive.google.com/file/d/{}/view".format(photo["id"])), use_container_width=True)

def render_upload():
    st.title("Share photos with DAAC")
    st.write("Every upload goes directly into permanent Google Drive storage. An organizer chooses its final event album.")
    with st.form("upload_form", clear_on_submit=True):
        left, right = st.columns(2)
        uploader = left.text_input("Your name *"); event = right.text_input("Event or project name *")
        category = st.selectbox("Suggested category *", CATEGORIES)
        photos = st.file_uploader("Photos *", type=IMAGE_TYPES, accept_multiple_files=True)
        notes = st.text_area("Notes (optional)")
        submit = st.form_submit_button("Send for approval", use_container_width=True)
    if not submit: return
    if not uploader.strip() or not event.strip() or not photos:
        st.error("Add your name, the event or project name, and at least one photo."); return
    if any(photo.size > 15 * 1024 * 1024 for photo in photos):
        st.error("Each photo must be 15 MB or smaller."); return
    files = [{"name": p.name, "mimeType": p.type or "image/jpeg", "base64": base64.b64encode(p.getvalue()).decode("ascii")} for p in photos]
    try:
        with st.spinner("Saving photos to Google Drive…"):
            app_script("upload", uploader=uploader.strip(), eventName=event.strip(), category=category, notes=notes.strip(), files=files)
        st.success("Received! The photos are waiting for approval.")
    except Exception as exc: st.error(f"Upload could not be completed: {exc}")

def render_review():
    st.title("Photos waiting for review")
    st.caption("Approving a batch creates or uses an event album inside the selected category.")
    try: batches = app_script("pending").get("batches", [])
    except Exception as exc: st.error(str(exc)); return
    if not batches: st.success("You are all caught up."); return
    for batch in batches:
        with st.container(border=True):
            st.subheader(batch.get("eventName") or "Untitled upload")
            st.caption(f"{batch.get('uploader') or 'DAAC team member'} · {len(batch['files'])} photo(s)")
            preview_photos = [p for p in batch["files"] if p.get("thumbnail")]
            if preview_photos:
                previews = st.columns(min(4, len(preview_photos)))
                for i, photo in enumerate(preview_photos):
                    previews[i % len(previews)].image(image_bytes(photo), caption=photo["name"], width=160)
            category = st.selectbox("Category", CATEGORIES, key=f"cat_{batch['id']}")
            approve, reject = st.columns(2)
            if approve.button("Approve into event album", type="primary", use_container_width=True, key=f"approve_{batch['id']}"):
                try: app_script("approve", batchId=batch["id"], category=category); st.rerun()
                except Exception as exc: st.error(str(exc))
            if reject.button("Move to Drive trash", use_container_width=True, key=f"reject_{batch['id']}"):
                try: app_script("reject", batchId=batch["id"]); st.rerun()
                except Exception as exc: st.error(str(exc))

st.markdown("""<style>
[data-testid="stAppViewContainer"]{background:linear-gradient(180deg,#eef9f8 0%,#fff 65%)} .block-container{max-width:1120px;padding-top:2rem;padding-bottom:5rem} h1,h2,h3{color:#176d73}.stButton>button,.stFormSubmitButton>button{border-radius:12px;font-weight:750}.photo-strip{overflow:hidden;padding:5px 0 18px;mask-image:linear-gradient(90deg,transparent,#000 4%,#000 96%,transparent)}.photo-track{display:flex;gap:16px;width:max-content;animation:slide 38s linear infinite}.photo-strip:hover .photo-track{animation-play-state:paused}.photo-strip a{text-decoration:none}.photo-strip figure{width:290px;margin:0;border-radius:18px;overflow:hidden;background:#fff;box-shadow:0 8px 20px #176d7320}.photo-strip img{width:290px;height:220px;object-fit:cover;display:block}.photo-strip figcaption{padding:10px 13px;color:#176d73;font-weight:700;font-size:.9rem}@keyframes slide{to{transform:translateX(-50%)}}
</style>""", unsafe_allow_html=True)

if "role" not in st.session_state: st.session_state.role = None
with st.sidebar:
    st.header("DAAC Photo Hub")
    pages = ["Album", "Upload", "Organizer review"]
    page = st.radio("Go to", pages, label_visibility="collapsed", key="page")
    if st.session_state.role:
        st.caption(f"Unlocked as {st.session_state.role}")
        if st.button("Lock app", use_container_width=True):
            st.session_state.role = None; st.rerun()
if page == "Album":
    render_album()
elif page == "Upload":
    render_upload()
elif page == "Organizer review" and st.session_state.role == "admin":
    render_review()
else:
    unlock()
