/**
 * Google Apps Script for VIP Telegram Subscription Management System (Sm-manager)
 * 
 * Instructions:
 * 1. Open your Google Sheet.
 * 2. Click Extensions -> Apps Script.
 * 3. Replace all code with this file.
 * 4. Click Deploy -> New deployment -> Web app.
 * 5. Execute as: "Me", Who has access: "Anyone".
 * 6. Copy the Web App URL and set it as GOOGLE_APPS_SCRIPT_URL in Render environment variables.
 */

var SECRET_KEY = "gas-sync-secret"; // Must match GOOGLE_APPS_SCRIPT_SECRET in backend

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return responseJSON({ status: "error", message: "No post data received" });
    }

    var data = JSON.parse(e.postData.contents);

    // Verify secret key
    if (data.secret !== SECRET_KEY) {
      return responseJSON({ status: "error", message: "Unauthorized: Invalid secret key" });
    }

    var ss = SpreadsheetApp.getActiveSpreadsheet();
    ensureSheetHeaders(ss);

    // Check idempotency if event_id is present
    if (data.event_id && isEventProcessed(ss, data.event_id)) {
      return responseJSON({ status: "success", message: "Event already processed (Idempotent)", event_id: data.event_id });
    }

    var eventType = data.event_type;
    var payload = data.payload || {};

    switch (eventType) {
      case "CUSTOMER_CREATED":
      case "CUSTOMER_UPDATED":
        upsertCustomer(ss, payload);
        break;

      case "TRANSACTION_CREATED":
      case "TRANSACTION_UPDATED":
      case "PAYMENT_SUBMITTED":
      case "PAYMENT_APPROVED":
      case "PAYMENT_REJECTED":
        upsertTransaction(ss, payload);
        break;

      case "SUBSCRIPTION_CREATED":
      case "SUBSCRIPTION_RENEWED":
      case "SUBSCRIPTION_EXTENDED":
      case "SUBSCRIPTION_EXPIRED":
        appendSubscriptionHistory(ss, payload);
        break;

      case "INVITE_CREATED":
      case "INVITE_USED":
      case "INVITE_REVOKED":
        upsertInviteHistory(ss, payload);
        break;

      case "MEMBERSHIP_EVENT":
      case "MEMBER_JOINED":
      case "MEMBER_LEFT":
      case "MEMBER_REMOVED":
        appendMembershipHistory(ss, payload);
        break;

      case "AUDIT_LOG":
        appendAuditLog(ss, payload);
        break;

      case "FULL_REBUILD":
        processFullRebuild(ss, payload);
        break;

      default:
        // Generic log
        appendAuditLog(ss, { actor: "BACKEND", action: eventType, details: JSON.stringify(payload) });
    }

    // Record processed event_id
    if (data.event_id) {
      recordProcessedEvent(ss, data.event_id, eventType);
    }

    return responseJSON({ status: "success", message: "Event processed successfully", event_id: data.event_id });

  } catch (err) {
    return responseJSON({ status: "error", message: err.toString() });
  }
}

function responseJSON(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function ensureSheetHeaders(ss) {
  createTabIfMissing(ss, "CUSTOMERS", [
    "customer_id", "telegram_id", "username", "first_name", "last_name", 
    "current_price", "status", "created_at", "last_activity"
  ]);

  createTabIfMissing(ss, "TRANSACTIONS", [
    "transaction_id", "customer_id", "telegram_id", "amount", "currency", 
    "utr", "payment_status", "plan_name", "submitted_at", "approved_at", 
    "rejected_at", "verified_by", "rejection_reason"
  ]);

  createTabIfMissing(ss, "SUBSCRIPTION_HISTORY", [
    "history_id", "customer_id", "transaction_id", "plan_name", "amount", 
    "start_date", "expiry_date", "event_type", "created_at"
  ]);

  createTabIfMissing(ss, "INVITE_HISTORY", [
    "invite_id", "customer_id", "telegram_id", "invite_url", "status", 
    "created_at", "used_at", "joined_telegram_id"
  ]);

  createTabIfMissing(ss, "MEMBERSHIP_HISTORY", [
    "event_id", "customer_id", "telegram_id", "channel_id", "event_type", 
    "invite_id", "event_time", "details"
  ]);

  createTabIfMissing(ss, "AUDIT_LOG", [
    "log_id", "timestamp", "actor", "action", "entity_type", "entity_id", "details"
  ]);

  createTabIfMissing(ss, "SYNC_EVENTS", [
    "event_id", "event_type", "processed_at"
  ]);
}

function createTabIfMissing(ss, sheetName, headers) {
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
    sheet.appendRow(headers);
    sheet.getRange(1, 1, 1, headers.length).setFontWeight("bold").setBackground("#e0e0e0");
  }
}

function isEventProcessed(ss, eventId) {
  var sheet = ss.getSheetByName("SYNC_EVENTS");
  if (!sheet) return false;
  var data = sheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (data[i][0] == eventId) {
      return true;
    }
  }
  return false;
}

function recordProcessedEvent(ss, eventId, eventType) {
  var sheet = ss.getSheetByName("SYNC_EVENTS");
  if (sheet) {
    sheet.appendRow([eventId, eventType, new Date().toISOString()]);
  }
}

function upsertCustomer(ss, p) {
  var sheet = ss.getSheetByName("CUSTOMERS");
  var data = sheet.getDataRange().getValues();
  var rowIdx = -1;
  for (var i = 1; i < data.length; i++) {
    if (data[i][0] == p.id || data[i][1] == p.telegram_id) {
      rowIdx = i + 1;
      break;
    }
  }
  var rowData = [
    p.id || "", p.telegram_id || "", p.username || "", p.first_name || "", p.last_name || "",
    p.custom_price !== undefined ? p.custom_price : "", p.status || "ACTIVE",
    p.created_at || new Date().toISOString(), p.last_activity || new Date().toISOString()
  ];
  if (rowIdx > 0) {
    sheet.getRange(rowIdx, 1, 1, rowData.length).setValues([rowData]);
  } else {
    sheet.appendRow(rowData);
  }
}

function upsertTransaction(ss, p) {
  var sheet = ss.getSheetByName("TRANSACTIONS");
  var data = sheet.getDataRange().getValues();
  var rowIdx = -1;
  for (var i = 1; i < data.length; i++) {
    if (data[i][0] == p.transaction_id) {
      rowIdx = i + 1;
      break;
    }
  }
  var rowData = [
    p.transaction_id || "", p.customer_id || "", p.telegram_id || "", p.amount || 0,
    p.currency || "INR", p.utr || "", p.payment_status || "", p.plan_name || "",
    p.submitted_at || "", p.approved_at || "", p.rejected_at || "",
    p.verified_by || "", p.rejection_reason || ""
  ];
  if (rowIdx > 0) {
    sheet.getRange(rowIdx, 1, 1, rowData.length).setValues([rowData]);
  } else {
    sheet.appendRow(rowData);
  }
}

function appendSubscriptionHistory(ss, p) {
  var sheet = ss.getSheetByName("SUBSCRIPTION_HISTORY");
  sheet.appendRow([
    p.history_id || p.subscription_id || "", p.customer_id || "", p.transaction_id || "",
    p.plan_name || "", p.amount || 0, p.start_date || "", p.expiry_date || "",
    p.event_type || "SUBSCRIPTION", p.created_at || new Date().toISOString()
  ]);
}

function upsertInviteHistory(ss, p) {
  var sheet = ss.getSheetByName("INVITE_HISTORY");
  var data = sheet.getDataRange().getValues();
  var rowIdx = -1;
  for (var i = 1; i < data.length; i++) {
    if (data[i][0] == p.invite_id) {
      rowIdx = i + 1;
      break;
    }
  }
  var rowData = [
    p.invite_id || "", p.customer_id || "", p.telegram_id || "", p.invite_url || "",
    p.status || "", p.created_at || "", p.used_at || "", p.joined_telegram_id || ""
  ];
  if (rowIdx > 0) {
    sheet.getRange(rowIdx, 1, 1, rowData.length).setValues([rowData]);
  } else {
    sheet.appendRow(rowData);
  }
}

function appendMembershipHistory(ss, p) {
  var sheet = ss.getSheetByName("MEMBERSHIP_HISTORY");
  sheet.appendRow([
    p.event_id || p.id || "", p.customer_id || "", p.telegram_id || "", p.channel_id || "",
    p.event_type || "", p.invite_id || "", p.event_time || new Date().toISOString(), p.details || ""
  ]);
}

function appendAuditLog(ss, p) {
  var sheet = ss.getSheetByName("AUDIT_LOG");
  sheet.appendRow([
    p.id || "", p.timestamp || new Date().toISOString(), p.actor || "SYSTEM",
    p.action || "", p.entity_type || "", p.entity_id || "", p.details || ""
  ]);
}

function processFullRebuild(ss, p) {
  if (p.customers) {
    var cSheet = ss.getSheetByName("CUSTOMERS");
    cSheet.clearContents();
    cSheet.appendRow(["customer_id", "telegram_id", "username", "first_name", "last_name", "current_price", "status", "created_at", "last_activity"]);
    p.customers.forEach(function(c) { upsertCustomer(ss, c); });
  }
  if (p.transactions) {
    var tSheet = ss.getSheetByName("TRANSACTIONS");
    tSheet.clearContents();
    tSheet.appendRow(["transaction_id", "customer_id", "telegram_id", "amount", "currency", "utr", "payment_status", "plan_name", "submitted_at", "approved_at", "rejected_at", "verified_by", "rejection_reason"]);
    p.transactions.forEach(function(t) { upsertTransaction(ss, t); });
  }
  if (p.subscriptions) {
    p.subscriptions.forEach(function(s) { appendSubscriptionHistory(ss, s); });
  }
}
