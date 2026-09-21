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
    url = setting("APPS_SCRIPT_URL")
    token = setting("APPS_SCRIPT_TOKEN")

    response = requests.post(
        url,
        json={"token": token, "action": action, **payload},
        timeout=90,
    )
    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Google Drive could not complete that request."))

    return data


def image_bytes(photo):
    return base64.b64decode(photo["thumbnail"]) if photo.get("thumbnail") else None


def go_upload():
    st.session_state.page = "Upload"


def unlock():
    st.markdown("### Organizer access")

    with st.form("access_form"):
        code = st.text_input("Admin code", type="password")
        submit = st.form_submit_button("Open organizer review", use_container_width=True)

    if submit:
        if secrets.compare_digest(code or "", str(setting("ADMIN_ACCESS_CODE") or "")):
            st.session_state.role = "admin"
            st.rerun()

        st.error("That admin code is not valid.")


def render_album():
    st.title("DAAC in the community")
    st.caption("A living record of DAAC’s events, projects, and partnerships.")

    st.button(
        "📷  Upload photos to DAAC",
        type="primary",
        use_container_width=True,
        on_click=go_upload,
    )

    try:
        gallery = app_script("gallery")
    except Exception as exc:
        st.error(str(exc))
        return

    featured = [photo for photo in gallery.get("featured", []) if photo.get("thumbnail")]

    st.markdown("## Latest from DAAC")

    if featured:
        cards = "".join(
            "<a href='{url}' target='_blank'>"
            "<figure><img src='data:image/jpeg;base64,{thumbnail}'>"
            "<figcaption>Open / download: {album}</figcaption>"
            "</figure></a>".format(
                url=photo.get(
                    "url",
                    "https://drive.google.com/file/d/{}/view".format(photo["id"]),
                ),
                thumbnail=photo["thumbnail"],
                album=photo.get("albumName", "DAAC"),
            )
            for photo in featured
        )

        st.markdown(
            f"<div class='photo-strip'><div class='photo-track'>{cards}{cards}</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("Photos will appear here once they are added to a DAAC event album.")

    st.markdown("## Explore photo albums")

    for album in gallery.get("albums", []):
        with st.expander(f"{album['name']}  ·  {album['count']} photos"):
            st.caption(album.get("category", ""))

            if album.get("url"):
                st.link_button(
                    "Open this full album and download photos",
                    album["url"],
                    use_container_width=True,
                )

            photos = [photo for photo in album.get("photos", []) if photo.get("thumbnail")]

            if not photos:
                st.caption("These photos do not have browser previews yet.")
            else:
                columns = st.columns(min(4, len(photos)))

                for index, photo in enumerate(photos):
                    column = columns[index % len(columns)]
                    column.image(image_bytes(photo), width=160)
                    column.link_button(
                        "Open / download full photo",
                        photo.get(
                            "url",
                            "https://drive.google.com/file/d/{}/view".format(photo["id"]),
                        ),
                        use_container_width=True,
                    )


def render_upload():
    st.title("Share photos with DAAC")
    st.write("Your photos go directly into DAAC’s permanent Google Drive intake folder.")

    with st.form("upload_form", clear_on_submit=True):
        left, right = st.columns(2)
        uploader = left.text_input("Your name *")
        event = right.text_input("Event or project name *")
        category = st.selectbox("Suggested category *", CATEGORIES)
        photos = st.file_uploader(
            "Photos *",
            type=IMAGE_TYPES,
            accept_multiple_files=True,
        )
        notes = st.text_area("Notes (optional)")
        submit = st.form_submit_button("Send for approval", use_container_width=True)

    if not submit:
        return

    if not uploader.strip() or not event.strip() or not photos:
        st.error("Add your name, the event or project name, and at least one photo.")
        return

    files = [
        {
            "name": photo.name,
            "mimeType": photo.type or "image/jpeg",
            "base64": base64.b64encode(photo.getvalue()).decode("ascii"),
        }
        for photo in photos
    ]

    try:
        with st.spinner("Saving photos to Google Drive…"):
            app_script(
                "upload",
                uploader=uploader.strip(),
                eventName=event.strip(),
                category=category,
                notes=notes.strip(),
                files=files,
            )

        st.success("Received! The photos are waiting for organizer approval.")
    except Exception as exc:
        st.error(str(exc))


def render_review():
    st.title("Photos waiting for review")
    st.caption("Preview each upload, then approve it into the correct event album.")

    try:
        batches = app_script("pending").get("batches", [])
    except Exception as exc:
        st.error(str(exc))
        return

    if not batches:
        st.success("You are all caught up.")
        return

    for batch in batches:
        with st.container(border=True):
            st.subheader(batch.get("eventName") or "Untitled upload")
            st.caption(
                f"{batch.get('uploader') or 'DAAC team member'} · "
                f"{len(batch['files'])} photo(s)"
            )

            preview_photos = [
                photo for photo in batch["files"] if photo.get("thumbnail")
            ]

            if preview_photos:
                previews = st.columns(min(4, len(preview_photos)))

                for index, photo in enumerate(preview_photos):
                    previews[index % len(previews)].image(
                        image_bytes(photo),
                        caption=photo["name"],
                        width=160,
                    )

            category = st.selectbox(
                "Category",
                CATEGORIES,
                key=f"cat_{batch['id']}",
            )

            approve, reject = st.columns(2)

            if approve.button(
                "Approve into event album",
                type="primary",
                use_container_width=True,
                key=f"approve_{batch['id']}",
            ):
                try:
                    app_script(
                        "approve",
                        batchId=batch["id"],
                        category=category,
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

            if reject.button(
                "Move to Drive trash",
                use_container_width=True,
                key=f"reject_{batch['id']}",
            ):
                try:
                    app_script("reject", batchId=batch["id"])
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(180deg, #eef9f8 0%, #ffffff 65%);
    }

    .block-container {
        max-width: 1120px;
        padding-top: 2rem;
        padding-bottom: 5rem;
    }

    h1, h2, h3 {
        color: #176d73;
    }

    .stButton > button, .stFormSubmitButton > button {
        border-radius: 12px;
        font-weight: 750;
    }

    .photo-strip {
        overflow: hidden;
        padding: 5px 0 18px;
    }

    .photo-track {
        display: flex;
        gap: 16px;
        width: max-content;
        animation: slide 38s linear infinite;
    }

    .photo-strip:hover .photo-track {
        animation-play-state: paused;
    }

    .photo-strip a {
        text-decoration: none;
    }

    .photo-strip figure {
        width: 290px;
        margin: 0;
        border-radius: 18px;
        overflow: hidden;
        background: white;
        box-shadow: 0 8px 20px #176d7320;
    }

    .photo-strip img {
        width: 290px;
        height: 220px;
        object-fit: cover;
        display: block;
    }

    .photo-strip figcaption {
        padding: 10px 13px;
        color: #176d73;
        font-weight: 700;
        font-size: 0.9rem;
    }

    @keyframes slide {
        to {
            transform: translateX(-50%);
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "role" not in st.session_state:
    st.session_state.role = None

with st.sidebar:
    st.header("DAAC Photo Hub")

    page = st.radio(
        "Go to",
        ["Album", "Upload", "Organizer review"],
        label_visibility="collapsed",
        key="page",
    )

    if st.session_state.role == "admin":
        if st.button("Lock organizer review", use_container_width=True):
            st.session_state.role = None
            st.rerun()

if page == "Album":
    render_album()
elif page == "Upload":
    render_upload()
elif st.session_state.role == "admin":
    render_review()
else:
    unlock()
