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
        timeout=180,
    )
    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Google Drive could not complete that request."))

    return data


def image_source(photo):
    if photo.get("thumbnail"):
        return "data:image/jpeg;base64," + photo["thumbnail"]
    return photo.get("thumbnailUrl")


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
    st.title("Welcome to DAAC Photo Hub")
    st.caption("A living record of DAAC’s events, projects, and partnerships.")

    st.markdown(
        """
        <div class="welcome-card">
            <div class="welcome-icon">📷</div>
            <div>
                <div class="welcome-title">Welcome to DAAC Photo Hub</div>
                <div class="welcome-text">Loading the latest DAAC photos and building your carousel…</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.button(
        "📷  Upload photos to DAAC",
        type="primary",
        use_container_width=True,
        on_click=go_upload,
    )

    try:
        with st.status("Loading DAAC photos…", expanded=True) as status:
            st.write("Connecting to the DAAC photo library…")
            gallery = app_script("gallery")
            st.write("Building the photo wall and carousel…")
            status.update(label="DAAC photos loaded", state="complete", expanded=False)
    except Exception as exc:
        st.error(f"We couldn't load the DAAC photo library: {exc}")
        return

    featured = [
        photo for photo in gallery.get("featured", [])
        if photo.get("thumbnail") or photo.get("thumbnailUrl")
    ]

    st.markdown("## 📸 DAAC Photo Carousel")

    if featured:
        cards = "".join(
            "<a href='{url}' target='_blank'>"
            "<figure><img src='{image}' loading='lazy'>"
            "<figcaption>{album}</figcaption>"
            "</figure></a>".format(
                url=photo.get(
                    "url",
                    "https://drive.google.com/file/d/{}/view".format(photo["id"]),
                ),
                image=image_source(photo),
                album=photo.get("albumName", "DAAC"),
            )
            for photo in featured
        )

        st.markdown(
            f"<div class='photo-strip'><div class='photo-track'>{cards}{cards}</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("Your approved photos will appear here.")

    st.markdown("## 🗂️ Explore DAAC Photo Albums")
    st.caption("Choose an album to browse its photos. Use the button inside each album to open the full Google Drive folder.")

    albums = gallery.get("albums", [])

    if not albums:
        st.info("No approved photo albums yet.")
        return

    # Square album-cover cards.
    album_cards = []
    for index, album in enumerate(albums):
        photos = album.get("photos", [])
        cover = next(
            (
                photo for photo in photos
                if photo.get("thumbnail") or photo.get("thumbnailUrl")
            ),
            None,
        )
        if not cover:
            continue

        album_cards.append(
            {
                "index": index,
                "name": album.get("name", "Untitled album"),
                "category": album.get("category", ""),
                "count": album.get("count", 0),
                "image": image_source(cover),
                "url": album.get("url", ""),
            }
        )

    if album_cards:
        columns = st.columns(4)
        for card in album_cards:
            column = columns[card["index"] % 4]
            with column:
                st.markdown(
                    f"""
                    <div class="album-card">
                        <img src="{card['image']}" loading="lazy">
                        <div class="album-card-title">{card['name']}</div>
                        <div class="album-card-meta">{card['category']} · {card['count']} photos</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Open album",
                    key=f"album_{card['index']}",
                    use_container_width=True,
                ):
                    st.session_state[f"open_album_{card['index']}"] = not st.session_state.get(
                        f"open_album_{card['index']}", False
                    )

    st.markdown("## 📂 Albums & Photos")

    for index, album in enumerate(albums):
        if not st.session_state.get(f"open_album_{index}", False):
            continue

        st.markdown(f"### {album['name']}")
        st.caption(f"{album.get('category', '')} · {album.get('count', 0)} photos")

        if album.get("url"):
            st.link_button(
                "Open full album in Google Drive",
                album["url"],
                use_container_width=True,
            )

        photos = album.get("photos", [])

        if not photos:
            st.info("No photos in this album.")
            continue

        columns = st.columns(4)
        for photo_index, photo in enumerate(photos):
            column = columns[photo_index % 4]
            with column:
                image = image_source(photo)
                if image:
                    st.image(image, width=220)
                st.caption(photo.get("albumName", album["name"]))
                st.link_button(
                    "Open / download",
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
                photo for photo in batch["files"]
                if photo.get("thumbnail") or photo.get("thumbnailUrl")
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

    .welcome-card {
        display: flex;
        align-items: center;
        gap: 18px;
        margin: 8px 0 22px;
        padding: 20px 22px;
        border-radius: 18px;
        background: white;
        box-shadow: 0 8px 24px #176d7320;
        border: 1px solid #176d7318;
    }

    .welcome-icon {
        font-size: 2.5rem;
    }

    .welcome-title {
        color: #176d73;
        font-size: 1.25rem;
        font-weight: 800;
    }

    .welcome-text {
        color: #4f6466;
        margin-top: 3px;
    }

    .album-card {\n        overflow: hidden;\n        border-radius: 16px;\n        background: white;\n        box-shadow: 0 8px 20px #176d7320;\n        margin-bottom: 10px;\n    }\n\n    .album-card img {\n        width: 100%;\n        aspect-ratio: 1 / 1;\n        object-fit: cover;\n        display: block;\n    }\n\n    .album-card-title {\n        padding: 10px 12px 2px;\n        color: #176d73;\n        font-weight: 800;\n    }\n\n    .album-card-meta {\n        padding: 2px 12px 12px;\n        color: #5d6b6d;\n        font-size: 0.82rem;\n    }\n\n    .photo-strip {
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
