/*
  DAAC Photo Hub — free Google Apps Script backend

  1. Open script.google.com and create a New project.
  2. Replace its Code.gs with this entire file.
  3. Replace CHANGE_THIS_TO_A_LONG_RANDOM_CODE below.
  4. Deploy > New deployment > Web app:
     Execute as: Me
     Who has access: Anyone
  5. Copy the Web app URL into Streamlit Secrets as APPS_SCRIPT_URL.
*/

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
  return reply({ok: true, message: 'DAAC Photo Hub is ready.'});
}

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents || '{}');
    if (data.token !== ACCESS_TOKEN) throw new Error('Access denied.');
    if (data.action === 'upload') return reply(upload(data));
    if (data.action === 'pending') return reply({ok: true, batches: pending()});
    if (data.action === 'approve') return reply(approve(data));
    if (data.action === 'reject') return reply(reject(data));
    if (data.action === 'album') return reply({ok: true, photos: album()});
    throw new Error('Unknown request.');
  } catch (error) {
    return reply({ok: false, error: error.message});
  }
}

function reply(value) {
  return ContentService.createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}

function batchMetadata(file) {
  try { return JSON.parse(file.getDescription() || '{}'); }
  catch (error) { return {}; }
}

function fileThumbnail(file) {
  const thumbnail = file.getThumbnail();
  return thumbnail ? Utilities.base64Encode(thumbnail.getBytes()) : null;
}

function upload(data) {
  if (!data.files || !data.files.length) throw new Error('No photos received.');
  const batchId = Utilities.getUuid();
  const folder = DriveApp.getFolderById(PENDING_FOLDER_ID);
  data.files.forEach(function(item) {
    const blob = Utilities.newBlob(Utilities.base64Decode(item.base64), item.mimeType || 'image/jpeg', item.name);
    const file = folder.createFile(blob);
    file.setDescription(JSON.stringify({
      batchId: batchId, uploader: data.uploader || '', eventName: data.eventName || '',
      suggestedCategory: data.category || 'Other / Needs Sorting', notes: data.notes || '',
      status: 'pending', createdAt: new Date().toISOString()
    }));
  });
  return {ok: true, batchId: batchId};
}

function pending() {
  const batches = {};
  const files = DriveApp.getFolderById(PENDING_FOLDER_ID).getFiles();
  while (files.hasNext()) {
    const file = files.next();
    const meta = batchMetadata(file);
    const id = meta.batchId || file.getId();
    if (!batches[id]) batches[id] = {
      id: id, uploader: meta.uploader || '', eventName: meta.eventName || '',
      suggestedCategory: meta.suggestedCategory || 'Other / Needs Sorting',
      notes: meta.notes || '', createdAt: meta.createdAt || '', files: []
    };
    batches[id].files.push({id: file.getId(), name: file.getName(), thumbnail: fileThumbnail(file)});
  }
  return Object.keys(batches).map(function(key) { return batches[key]; })
    .sort(function(a, b) { return (b.createdAt || '').localeCompare(a.createdAt || ''); });
}

function filesForBatch(batchId) {
  const matches = [];
  const files = DriveApp.getFolderById(PENDING_FOLDER_ID).getFiles();
  while (files.hasNext()) {
    const file = files.next();
    if (batchMetadata(file).batchId === batchId) matches.push(file);
  }
  return matches;
}

function approve(data) {
  if (!CATEGORY_FOLDERS[data.category]) throw new Error('Choose a valid destination folder.');
  const files = filesForBatch(data.batchId);
  if (!files.length) throw new Error('That pending batch was not found.');
  const pendingFolder = DriveApp.getFolderById(PENDING_FOLDER_ID);
  const destination = DriveApp.getFolderById(CATEGORY_FOLDERS[data.category]);
  files.forEach(function(file) {
    const meta = batchMetadata(file);
    meta.status = 'approved'; meta.approvedCategory = data.category;
    meta.albumVisible = Boolean(data.albumVisible); meta.approvedAt = new Date().toISOString();
    file.setDescription(JSON.stringify(meta));
    destination.addFile(file);
    pendingFolder.removeFile(file);
  });
  return {ok: true};
}

function reject(data) {
  const files = filesForBatch(data.batchId);
  if (!files.length) throw new Error('That pending batch was not found.');
  files.forEach(function(file) { file.setTrashed(true); });
  return {ok: true};
}

function album() {
  const photos = [];
  Object.keys(CATEGORY_FOLDERS).forEach(function(category) {
    const files = DriveApp.getFolderById(CATEGORY_FOLDERS[category]).getFiles();
    while (files.hasNext()) {
      const file = files.next();
      const meta = batchMetadata(file);
      if (meta.status === 'approved' && meta.albumVisible === true) {
        photos.push({id: file.getId(), category: category, createdAt: meta.approvedAt || '', thumbnail: fileThumbnail(file)});
      }
    }
  });
  return photos.sort(function(a, b) { return (b.createdAt || '').localeCompare(a.createdAt || ''); }).slice(0, 24);
}
