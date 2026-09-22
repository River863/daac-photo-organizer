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

    if not url:
        raise RuntimeError("APPS_SCRIPT_URL is not configured.")
    if not token:
        raise RuntimeError("APPS_SCRIPT_TOKEN is not configured.")

    response = requests.post(
        url,
        json={"token": token, "action": action, **payload},
        timeout=180,
    )
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError:
        body = response.text.strip()
        preview = body[:300] if body else "(empty response)"
        raise RuntimeError(
            "Google Apps Script returned a non-JSON response "
            f"for '{action}'. Response: {preview}"
        )

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Google Apps Script returned an unexpected response for '{action}'."
        )

    if not data.get("ok"):
        raise RuntimeError(
            data.get("error", "Google Drive could not complete that request.")
        )

    return data


@st.cache_data(ttl=300, show_spinner=False)
def load_gallery():
    return app_script("gallery")


@st.cache_data(ttl=300, show_spinner=False)
def load_album(folder_id, category):
    return app_script("album", folderId=folder_id, category=category)


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


@st.dialog("DAAC Photo Album")
def show_album_lightbox(album):
    photos = album.get("photos", [])

    if not photos:
        st.info("This album has no photos.")
        return

    album_name = album.get("name", "DAAC Album")
    st.subheader(album_name)
    st.caption(
        f"{album.get('category', '')} · {len(photos)} photos"
    )

    index = st.session_state.get("lightbox_photo_index", 0)
    index = max(0, min(index, len(photos) - 1))
    photo = photos[index]

    try:
        preview = app_script("photo", fileId=photo["id"])
        image = "data:image/jpeg;base64," + preview["image"]
        st.image(image, use_container_width=True)
    except Exception:
        image = image_source(photo)
        if image:
            st.image(image, use_container_width=True)
        else:
            st.warning("This photo could not be previewed.")

    st.caption(f"Photo {index + 1} of {len(photos)}")

    previous, download, next_button = st.columns(3)

    with previous:
        if st.button(
            "← Previous",
            use_container_width=True,
            disabled=index == 0,
        ):
            st.session_state.lightbox_photo_index = index - 1
            st.rerun()

    with download:
        st.link_button(
            "Open / download original",
            photo.get(
                "url",
                "https://drive.google.com/file/d/{}/view".format(photo["id"]),
            ),
            use_container_width=True,
        )

    with next_button:
        if st.button(
            "Next →",
            use_container_width=True,
            disabled=index == len(photos) - 1,
        ):
            st.session_state.lightbox_photo_index = index + 1
            st.rerun()

    st.markdown("### All photos in this album")

    thumbs = st.columns(5)

    for photo_index, item in enumerate(photos):
        with thumbs[photo_index % 5]:
            thumb = image_source(item)
            if thumb:
                st.image(thumb, use_container_width=True)

            if st.button(
                str(photo_index + 1),
                key=f"lightbox_thumb_{album_name}_{photo_index}",
                use_container_width=True,
            ):
                st.session_state.lightbox_photo_index = photo_index
                st.rerun()

    if album.get("url"):
        st.link_button(
            "Open complete Google Drive folder",
            album["url"],
            use_container_width=True,
        )


def render_album():
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "daac-logo.svg")
    if os.path.exists(logo_path):
        logo_left, logo_center, logo_right = st.columns([1, 2, 1])
        with logo_center:
            st.image(logo_path, use_container_width=True)

    st.title("DAAC – Del Amo Action Committee")
    st.caption(
        "A photo album of DAAC’s events, projects, and community work."
    )

    st.markdown(
        """
        <div class="welcome-card">
            <div class="welcome-icon">📷</div>
            <div>
                <div class="welcome-title">DAAC – Del Amo Action Committee</div>
                <div class="welcome-text">
                    A photo album of DAAC’s events, projects, and community work.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.button(
        "📷 Upload photos to DAAC",
        type="primary",
        use_container_width=True,
        on_click=go_upload,
    )

    try:
        with st.status(
            "Loading DAAC photos…",
            expanded=True
        ) as status:

            st.markdown(
                """
                <div class="loading-card">
                    <div class="loading-logo">📷</div>
                    <div class="loading-title">Loading the DAAC Photo Album</div>
                    <div class="loading-text">
                        Pulling in the latest events and photos. Please stay on this page.
                    </div>
                    <div class="loading-dots"><span></span><span></span><span></span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.write("Connecting to the DAAC photo library…")
            gallery = load_gallery()
            st.write("Building your carousel and album covers…")

            status.update(
                label="Photo album ready!",
                state="complete",
                expanded=False,
            )

    except Exception as exc:
        st.error(
            f"We couldn't load the DAAC photo library: {exc}"
        )
        return

    featured = [
        photo
        for photo in gallery.get("featured", [])
        if photo.get("thumbnail") or photo.get("thumbnailUrl")
    ]

    albums = gallery.get("albums", [])

    st.markdown("## 📸 Latest DAAC Photos")

    if featured:
        cards = "".join(
            """
            <a href="{url}" target="_blank" class="carousel-card">
                <img src="{image}" loading="lazy">
                <div class="carousel-caption">{album}</div>
            </a>
            """.format(
                url=photo.get(
                    "url",
                    "https://drive.google.com/file/d/{}/view".format(
                        photo["id"]
                    ),
                ),
                image=image_source(photo),
                album=photo.get("albumName", "DAAC"),
            )
            for photo in featured
        )

        st.markdown(
            f"""
            <div class="photo-strip">
                <div class="photo-track">
                    {cards}{cards}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info(
            "Your approved photos will appear here."
        )

    st.markdown("## 🗂️ DAAC Photo Albums")
    st.caption(
        "Click an album to open its photo lightbox."
    )

    if not albums:
        st.info("No approved photo albums yet.")
        return

    columns = st.columns(4)

    for album_index, album in enumerate(albums):
        cover = album.get("cover")

        if not cover:
            continue

        with columns[album_index % 4]:
            cover_image = image_source(cover)

            if cover_image:
                st.markdown(
                    f"""
                    <div class="album-card">
                        <img
                            src="{cover_image}"
                            loading="lazy"
                        >
                        <div class="album-card-body">
                            <div class="album-card-title">
                                {album.get("name", "Untitled Album")}
                            </div>
                            <div class="album-card-meta">
                                {album.get("category", "")}
                                · {album.get("count", 0)} photos
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            if st.button(
                "View album",
                key=f"open_album_{album_index}",
                use_container_width=True,
                type="primary",
            ):
                st.session_state.selected_album = album_index
                st.session_state.lightbox_photo_index = 0
                st.rerun()

    selected_album = st.session_state.get(
        "selected_album"
    )

    if (
        selected_album is not None
        and 0 <= selected_album < len(albums)
    ):
        selected = albums[selected_album]

        try:
            with st.spinner("Opening this album…"):
                full_album = load_album(
                    selected["id"],
                    selected.get("category", "")
                )
            show_album_lightbox(full_album)
        except Exception as exc:
            st.error(
                f"We couldn't open this album: {exc}"
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

        load_gallery.clear()
        load_album.clear()
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
                    load_gallery.clear()
                    load_album.clear()
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
                    load_gallery.clear()
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

    .loading-card {
        margin: 10px 0 22px;
        padding: 34px 24px;
        text-align: center;
        border-radius: 22px;
        background: white;
        border: 1px solid #176d7320;
        box-shadow: 0 10px 30px #176d7318;
    }

    .loading-logo {
        font-size: 2.8rem;
        margin-bottom: 6px;
    }

    .loading-title {
        color: #176d73;
        font-size: 1.35rem;
        font-weight: 800;
    }

    .loading-text {
        color: #5d6b6d;
        margin-top: 6px;
        font-size: 0.95rem;
    }

    .loading-dots {
        display: flex;
        justify-content: center;
        gap: 7px;
        margin-top: 18px;
    }

    .loading-dots span {
        width: 9px;
        height: 9px;
        border-radius: 50%;
        background: #176d73;
        animation: loadingPulse 1.2s infinite ease-in-out;
    }

    .loading-dots span:nth-child(2) {
        animation-delay: 0.15s;
    }

    .loading-dots span:nth-child(3) {
        animation-delay: 0.3s;
    }

    @keyframes loadingPulse {
        0%, 80%, 100% { opacity: 0.25; transform: scale(0.75); }
        40% { opacity: 1; transform: scale(1); }
    }

    .album-card {
        overflow: hidden;
        border-radius: 18px;
        background: white;
        box-shadow: 0 8px 22px #176d7320;
        margin-bottom: 10px;
        border: 1px solid #176d7318;
    }

    .album-card img {
        width: 100%;
        aspect-ratio: 1 / 1;
        object-fit: cover;
        display: block;
    }

    .album-card-body {
        padding: 12px 14px 14px;
    }

    .album-card-title {
        color: #176d73;
        font-weight: 800;
        font-size: 1rem;
    }

    .album-card-meta {
        color: #5d6b6d;
        font-size: 0.82rem;
        margin-top: 3px;
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
