const ACCESS_TOKEN = 'CHANGE_THIS_TO_A_LONG_RANDOM_CODE';

const PENDING_FOLDER_ID = '1HFbufjJ10tvxcA0ri8SP3cm0rIg5gRD2';

const CATEGORY_FOLDERS = {
  'Open Houses': '1B7N_ypgTPFEInp-w_drbnxpub5hhVG1N',
  'Community Events': '1u-Obz83I88rFPtXuiuyEtzfcfzWsMbWH',
  'Environmental & Community Projects': '1yJl5Lwsj9EqLy1DC_g1F1r9XbPISbiDr',
  'Outreach & Partnerships': '1G2n-8p4cdOYSyJ8-x6dQWX_NY9PirYEn',
  'Social Media': '1HUSk5mwaDW4jAMp6sGYZbJ_2cd2y43mR',
  'Other / Needs Sorting': '1AjD8dOem0T601hbwMnnABuBMDzG5WNv5'
};

function doGet() {
  return reply({ ok: true, message: 'DAAC Photo Hub is ready.' });
}

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents || '{}');

    if (data.token !== ACCESS_TOKEN) {
      throw new Error('Access denied.');
    }

    if (data.action === 'upload') return reply(upload(data));
    if (data.action === 'pending') return reply({ ok: true, batches: pending() });
    if (data.action === 'approve') return reply(approve(data));
    if (data.action === 'reject') return reply(reject(data));
    if (data.action === 'gallery') return reply({ ok: true, ...gallery() });
    if (data.action === 'photo') return reply(photo(data));

    throw new Error('Unknown request.');
  } catch (error) {
    return reply({ ok: false, error: error.message });
  }
}

function reply(value) {
  return ContentService
    .createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}

function metadata(file) {
  try {
    return JSON.parse(file.getDescription() || '{}');
  } catch (error) {
    return {};
  }
}

function thumbnail(file) {
  try {
    const image = file.getThumbnail();
    return image ? Utilities.base64Encode(image.getBytes()) : null;
  } catch (error) {
    return null;
  }
}

function photo(data) {
  if (!data.fileId) {
    throw new Error('No photo ID provided.');
  }

  const file = DriveApp.getFileById(data.fileId);
  const image = thumbnail(file);

  if (!image) {
    throw new Error('Preview could not be generated for this photo.');
  }

  return {
    ok: true,
    id: file.getId(),
    name: file.getName(),
    mimeType: file.getMimeType(),
    image: image
  };
}

function thumbnailUrl(file) {
  return 'https://drive.google.com/thumbnail?id=' + encodeURIComponent(file.getId()) + '&sz=w1000'; 
}

function upload(data) {
  if (!data.files || !data.files.length) {
    throw new Error('No photos received.');
  }

  const batchId = Utilities.getUuid();
  const folder = DriveApp.getFolderById(PENDING_FOLDER_ID);

  data.files.forEach(function(item) {
    const file = folder.createFile(
      Utilities.newBlob(
        Utilities.base64Decode(item.base64),
        item.mimeType || 'image/jpeg',
        item.name
      )
    );

    file.setDescription(JSON.stringify({
      batchId: batchId,
      uploader: data.uploader || '',
      eventName: data.eventName || '',
      suggestedCategory: data.category || 'Other / Needs Sorting',
      notes: data.notes || '',
      status: 'pending',
      createdAt: new Date().toISOString()
    }));
  });

  return { ok: true, batchId: batchId };
}

function pending() {
  const groups = {};
  const files = DriveApp.getFolderById(PENDING_FOLDER_ID).getFiles();

  while (files.hasNext()) {
    const file = files.next();
    const meta = metadata(file);
    const id = meta.batchId || file.getId();

    if (!groups[id]) {
      groups[id] = {
        id: id,
        uploader: meta.uploader || '',
        eventName: meta.eventName || '',
        suggestedCategory: meta.suggestedCategory || 'Other / Needs Sorting',
        notes: meta.notes || '',
        createdAt: meta.createdAt || '',
        files: []
      };
    }

    groups[id].files.push({
      id: file.getId(),
      name: file.getName(),
      thumbnail: thumbnail(file),
      thumbnailUrl: thumbnailUrl(file)
    });
  }

  return Object.keys(groups)
    .map(function(id) { return groups[id]; })
    .sort(function(a, b) {
      return (b.createdAt || '').localeCompare(a.createdAt || '');
    });
}

function batchFiles(batchId) {
  const matches = [];
  const files = DriveApp.getFolderById(PENDING_FOLDER_ID).getFiles();

  while (files.hasNext()) {
    const file = files.next();

    if (metadata(file).batchId === batchId) {
      matches.push(file);
    }
  }

  return matches;
}

function eventFolder(category, eventName) {
  const parent = DriveApp.getFolderById(CATEGORY_FOLDERS[category]);
  const name = (eventName || 'Untitled event').trim();
  const folders = parent.getFoldersByName(name);

  return folders.hasNext() ? folders.next() : parent.createFolder(name);
}

function approve(data) {
  if (!CATEGORY_FOLDERS[data.category]) {
    throw new Error('Choose a valid category.');
  }

  const files = batchFiles(data.batchId);

  if (!files.length) {
    throw new Error('That pending batch was not found.');
  }

  const target = eventFolder(data.category, metadata(files[0]).eventName);
  const pendingFolder = DriveApp.getFolderById(PENDING_FOLDER_ID);

  files.forEach(function(file) {
    const meta = metadata(file);
    meta.status = 'approved';
    meta.approvedCategory = data.category;
    meta.approvedAt = new Date().toISOString();

    file.setDescription(JSON.stringify(meta));
    target.addFile(file);
    pendingFolder.removeFile(file);
  });

  return { ok: true };
}

function reject(data) {
  const files = batchFiles(data.batchId);

  if (!files.length) {
    throw new Error('That pending batch was not found.');
  }

  files.forEach(function(file) {
    file.setTrashed(true);
  });

  return { ok: true };
}

function photoRecord(file, category, albumName, includeThumbnail) {
  return {
    id: file.getId(),
    category: category,
    albumName: albumName,
    createdAt: file.getDateCreated().toISOString(),
    thumbnail: includeThumbnail ? thumbnail(file) : null,
    thumbnailUrl: thumbnailUrl(file),
    url: file.getUrl()
  };
}

function filesInFolder(folder, category, albumName, limit) {
  const photos = [];
  const files = folder.getFiles();

  while (files.hasNext()) {
    const file = files.next();

    if (file.getMimeType().indexOf('image/') === 0) {
      const record = photoRecord(file, category, albumName, false);

      // Generate one cover preview per album only.
      if (photos.length === 0) {
        record.thumbnail = thumbnail(file);
      }

      photos.push(record);
    }
  }

  return photos;
}

function gallery() {
  const albums = [];
  const featured = [];

  Object.keys(CATEGORY_FOLDERS).forEach(function(category) {
    const folder = DriveApp.getFolderById(CATEGORY_FOLDERS[category]);
    const childFolders = folder.getFolders();

    while (childFolders.hasNext()) {
      const child = childFolders.next();
      const photos = filesInFolder(child, category, child.getName(), 8);

      if (photos.length) {
        const albumPhotos = photos;

        albums.push({
          name: child.getName(),
          category: category,
          count: albumPhotos.length,
          photos: albumPhotos,
          url: child.getUrl()
        });

        photos.forEach(function(item) {
          featured.push(item);
        });
      }
    }
  });

  featured.sort(function(a, b) {
    return b.createdAt.localeCompare(a.createdAt);
  });

  albums.sort(function(a, b) {
    return b.photos[0].createdAt.localeCompare(a.photos[0].createdAt);
  });

  const featuredRecords = featured.slice(0, 8).map(function(photo) {
    if (!photo.thumbnail) {
      const file = DriveApp.getFileById(photo.id);
      photo.thumbnail = thumbnail(file);
    }
    return photo;
  });

  return {
    featured: featuredRecords,
    albums: albums
  };
}