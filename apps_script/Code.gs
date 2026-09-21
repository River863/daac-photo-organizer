const ACCESS_TOKEN = 'DAACphotoBridge_7pH3mK9xQ2wL6z';
const PENDING_FOLDER_ID = '1HFbufjJ10tvxcA0ri8SP3cm0rIg5gRD2';
const CATEGORY_FOLDERS = {
  'Open Houses': '1B7N_ypgTPFEInp-w_drbnxpub5hhVG1N',
  'Community Events': '1u-Obz83I88rFPtXuiuyEtzfcfzWsMbWH',
  'Environmental & Community Projects': '1yJl5Lwsj9EqLy1DC_g1F1r9XbPISbiDr',
  'Outreach & Partnerships': '1G2n-8p4cdOYSyJ8-x6dQWX_NY9PirYEn',
  'Social Media': '1HUSk5mwaDW4jAMp6sGYZbJ_2cd2y43mR',
  'Other / Needs Sorting': '1AjD8dOem0T601hbwMnnABuBMDzG5WNv5'
};

function doGet() { return reply({ok: true, message: 'DAAC Photo Hub is ready.'}); }

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents || '{}');
    if (data.token !== ACCESS_TOKEN) throw new Error('Access denied.');
    if (data.action === 'upload') return reply(upload(data));
    if (data.action === 'pending') return reply({ok: true, batches: pending()});
    if (data.action === 'approve') return reply(approve(data));
    if (data.action === 'reject') return reply(reject(data));
    if (data.action === 'gallery') return reply({ok: true, ...gallery()});
    throw new Error('Unknown request.');
  } catch (error) { return reply({ok: false, error: error.message}); }
}

function reply(value) {
  return ContentService.createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}

function metadata(file) {
  try { return JSON.parse(file.getDescription() || '{}'); }
  catch (error) { return {}; }
}

function thumbnail(file) {
  const image = file.getThumbnail();
  return image ? Utilities.base64Encode(image.getBytes()) : null;
}

function upload(data) {
  if (!data.files || !data.files.length) throw new Error('No photos received.');
  const batchId = Utilities.getUuid();
  const folder = DriveApp.getFolderById(PENDING_FOLDER_ID);
  data.files.forEach(function(item) {
    const file = folder.createFile(Utilities.newBlob(
      Utilities.base64Decode(item.base64), item.mimeType || 'image/jpeg', item.name
    ));
    file.setDescription(JSON.stringify({
      batchId: batchId, uploader: data.uploader || '', eventName: data.eventName || '',
      suggestedCategory: data.category || 'Other / Needs Sorting', notes: data.notes || '',
      status: 'pending', createdAt: new Date().toISOString()
    }));
  });
  return {ok: true, batchId: batchId};
}

function pending() {
  const groups = {};
  const files = DriveApp.getFolderById(PENDING_FOLDER_ID).getFiles();
  while (files.hasNext()) {
    const file = files.next(), meta = metadata(file), id = meta.batchId || file.getId();
    if (!groups[id]) groups[id] = {
      id: id, uploader: meta.uploader || '', eventName: meta.eventName || '',
      suggestedCategory: meta.suggestedCategory || 'Other / Needs Sorting',
      notes: meta.notes || '', createdAt: meta.createdAt || '', files: []
    };
    groups[id].files.push({id: file.getId(), name: file.getName(), thumbnail: thumbnail(file)});
  }
  return Object.keys(groups).map(function(id) { return groups[id]; })
    .sort(function(a, b) { return (b.createdAt || '').localeCompare(a.createdAt || ''); });
}

function batchFiles(batchId) {
  const matches = [], files = DriveApp.getFolderById(PENDING_FOLDER_ID).getFiles();
  while (files.hasNext()) {
    const file = files.next();
    if (metadata(file).batchId === batchId) matches.push(file);
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
  if (!CATEGORY_FOLDERS[data.category]) throw new Error('Choose a valid category.');
  const files = batchFiles(data.batchId);
  if (!files.length) throw new Error('That pending batch was not found.');
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
  return {ok: true};
}

function reject(data) {
  const files = batchFiles(data.batchId);
  if (!files.length) throw new Error('That pending batch was not found.');
  files.forEach(function(file) { file.setTrashed(true); });
  return {ok: true};
}

function photoRecord(file, category, albumName) {
  return {
    id: file.getId(), category: category, albumName: albumName,
    createdAt: file.getDateCreated().toISOString(), thumbnail: thumbnail(file)
  };
}

function filesInFolder(folder, category, albumName, limit) {
  const photos = [], files = folder.getFiles();
  while (files.hasNext() && photos.length < limit) {
    const file = files.next();
    if (file.getMimeType().indexOf('image/') === 0) photos.push(photoRecord(file, category, albumName));
  }
  return photos;
}

function gallery() {
  const albums = [], featured = [];
  Object.keys(CATEGORY_FOLDERS).forEach(function(category) {
    const folder = DriveApp.getFolderById(CATEGORY_FOLDERS[category]);
    const directPhotos = filesInFolder(folder, category, category, 8);
    if (directPhotos.length) albums.push({name: category, category: category, count: directPhotos.length, photos: directPhotos});
    const childFolders = folder.getFolders();
    while (childFolders.hasNext()) {
      const child = childFolders.next();
      const photos = filesInFolder(child, category, child.getName(), 8);
      if (photos.length) albums.push({name: child.getName(), category: category, count: photos.length, photos: photos});
    }
  });
  albums.forEach(function(album) { album.photos.forEach(function(photo) { featured.push(photo); }); });
  featured.sort(function(a, b) { return b.createdAt.localeCompare(a.createdAt); });
  albums.sort(function(a, b) { return b.photos[0].createdAt.localeCompare(a.photos[0].createdAt); });
  return {featured: featured.slice(0, 8), albums: albums};
}