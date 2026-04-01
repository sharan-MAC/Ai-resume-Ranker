import imap from 'imap-simple';
import { simpleParser } from 'mailparser';
import { settings } from '../core/config';
import { queryOne, runQuery } from '../db/session';
import { processResumeLogic } from './resumeProcessor';
import fs from 'fs';
import path from 'path';
import nodemailer from 'nodemailer';

export const RESUMES_RAW_DIR = path.join(process.cwd(), 'resumes_raw');
if (!fs.existsSync(RESUMES_RAW_DIR)) {
  fs.mkdirSync(RESUMES_RAW_DIR);
}

export const getHREmail = async () => {
  const row = await queryOne("SELECT value FROM settings WHERE key = 'hr_email'");
  return row?.value || settings.HR_EMAIL;
};

export const sendNotificationEmail = async (subject: string, body: string) => {
  const emailSetting = await queryOne("SELECT value FROM settings WHERE key = 'email_notifications'");
  if (emailSetting?.value === 'false') {
    console.log("[EMAIL NOTIFICATION] Email notifications are disabled in settings. Skipping.");
    return;
  }

  const hrEmail = await getHREmail();
  console.log(`[EMAIL NOTIFICATION] To: ${hrEmail}, Subject: ${subject}`);
  
  const rawUser = settings.EMAIL_USER;
  const rawPass = settings.EMAIL_PASS;

  if (!rawUser || !rawPass || rawPass === 'YOUR_GMAIL_APP_PASSWORD') {
    console.log("[EMAIL NOTIFICATION] Email credentials not configured. Skipping real email send.");
    return;
  }

  const userEmail = rawUser.trim().replace(/^["']|["']$/g, '');
  const cleanPassword = rawPass.trim().replace(/\s+/g, '').replace(/^["']|["']$/g, '');

  try {
    const transporter = nodemailer.createTransport({
      host: settings.SMTP_HOST,
      port: settings.SMTP_PORT,
      secure: settings.SMTP_PORT === 465,
      auth: {
        user: userEmail,
        pass: cleanPassword,
      },
    });

    await transporter.sendMail({
      from: `"Recruit.AI" <${userEmail}>`,
      to: hrEmail,
      subject: `[Recruit.AI] ${subject}`,
      text: body,
    });

    console.log(`[EMAIL NOTIFICATION] Successfully sent email to ${hrEmail}`);
  } catch (err) {
    console.error(`[EMAIL NOTIFICATION] Failed to send email:`, err);
  }
};

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export const testEmailConnection = async () => {
  const rawUser = settings.EMAIL_USER;
  const rawPass = settings.EMAIL_PASS;

  if (!rawUser || !rawPass || rawPass === 'YOUR_GMAIL_APP_PASSWORD') {
    return { success: false, error: "Email credentials not configured or placeholder detected." };
  }

  // Clean credentials: remove whitespace and potential quotes
  const userEmail = rawUser.trim().replace(/^["']|["']$/g, '');
  const cleanPassword = rawPass.trim().replace(/\s+/g, '').replace(/^["']|["']$/g, '');

  const maskedEmail = userEmail.length > 5 
    ? `${userEmail.substring(0, 3)}...${userEmail.substring(userEmail.indexOf('@') - 2)}`
    : '***';
  const maskedPass = cleanPassword.length > 2 
    ? `${cleanPassword[0]}...${cleanPassword[cleanPassword.length-1]}` 
    : '***';
  console.log(`[INGESTION] Testing connection for user: ${maskedEmail}, host: ${settings.EMAIL_HOST}, port: ${settings.EMAIL_PORT}`);
  console.log(`[INGESTION] Diagnostic: Email length=${userEmail.length}, Password length=${cleanPassword.length}, MaskedPass=${maskedPass}`);

  if (settings.EMAIL_HOST?.toLowerCase().includes('smtp')) {
    return { success: false, error: `Invalid EMAIL_HOST: ${settings.EMAIL_HOST}. You are using an SMTP host for an IMAP connection. Please use imap.gmail.com instead.` };
  }

  if (cleanPassword.length !== 16 && settings.EMAIL_HOST?.includes('gmail')) {
    console.warn(`[INGESTION] Warning: App Password length is ${cleanPassword.length}, expected 16 for Gmail.`);
  }

  const config = {
    imap: {
      user: userEmail,
      password: cleanPassword,
      host: settings.EMAIL_HOST,
      port: settings.EMAIL_PORT,
      tls: true,
      tlsOptions: { rejectUnauthorized: false },
      authTimeout: 30000,
      connTimeout: 30000,
    }
  };

  try {
    const connection = await imap.connect(config);
    connection.end();
    return { success: true, message: "Connection successful!" };
  } catch (err: any) {
    const errMsg = err.message || String(err);
    console.error(`[INGESTION] Connection test failed:`, errMsg);
    if (err.textCode === 'AUTHENTICATIONFAILED' || errMsg.includes('Invalid credentials') || errMsg.includes('Authentication failed')) {
      return { 
        success: false, 
        error: "Authentication failed. \n" +
               "1. If using Gmail, you MUST use a 16-character 'App Password' (not your regular password).\n" +
               "2. Ensure IMAP is enabled in Gmail settings (Forwarding and POP/IMAP tab).\n" +
               "3. Check if your email address is correct."
      };
    }
    return { success: false, error: `Connection failed: ${errMsg}` };
  }
};

export const performIngestion = async (retryCount = 3) => {
  const rawUser = settings.EMAIL_USER;
  const rawPass = settings.EMAIL_PASS;

  if (!rawUser || !rawPass || rawPass === 'YOUR_GMAIL_APP_PASSWORD') {
    console.log("[INGESTION] Email credentials not configured or placeholder detected. Skipping ingestion.");
    return { success: false, message: "Email not configured" };
  }

  const hrEmail = await getHREmail();

  // Clean credentials: remove whitespace and potential quotes
  const userEmail = rawUser.trim().replace(/^["']|["']$/g, '');
  const cleanPassword = rawPass.trim().replace(/\s+/g, '').replace(/^["']|["']$/g, '');

  const maskedEmail = userEmail.length > 5 
    ? `${userEmail.substring(0, 3)}...${userEmail.substring(userEmail.indexOf('@') - 2)}`
    : '***';
  const maskedPass = cleanPassword.length > 2 
    ? `${cleanPassword[0]}...${cleanPassword[cleanPassword.length-1]}` 
    : '***';
  console.log(`[INGESTION] Initializing ingestion for user: ${maskedEmail}, host: ${settings.EMAIL_HOST}, port: ${settings.EMAIL_PORT}`);
  console.log(`[INGESTION] Diagnostic: Email length=${userEmail.length}, Password length=${cleanPassword.length}, MaskedPass=${maskedPass}`);

  if (settings.EMAIL_HOST?.toLowerCase().includes('smtp')) {
    console.error(`[INGESTION] Error: Invalid EMAIL_HOST: ${settings.EMAIL_HOST}. Using SMTP host for IMAP connection.`);
    return { success: false, message: "Invalid email host configuration" };
  }

  if (cleanPassword.length !== 16 && settings.EMAIL_HOST?.includes('gmail')) {
    console.warn(`[INGESTION] Warning: App Password length is ${cleanPassword.length}, expected 16 for Gmail.`);
  }

  const config = {
    imap: {
      user: userEmail,
      password: cleanPassword,
      host: settings.EMAIL_HOST,
      port: settings.EMAIL_PORT,
      tls: true,
      tlsOptions: { rejectUnauthorized: false },
      authTimeout: 30000,
      connTimeout: 30000,
    }
  };

  let connection: any;
  let attempt = 0;

  while (attempt < retryCount) {
    try {
      attempt++;
      console.log(`[INGESTION] Connection attempt ${attempt}/${retryCount} to ${settings.EMAIL_HOST} as ${userEmail}...`);
      connection = await imap.connect(config);
      break; // Success
    } catch (err: any) {
      const errMsg = err.message || String(err);
      console.error(`[INGESTION] Connection attempt ${attempt} failed:`, errMsg);
      
      if (err.textCode === 'AUTHENTICATIONFAILED' || errMsg.includes('Invalid credentials') || errMsg.includes('Authentication failed')) {
        return { 
          success: false, 
          error: "Authentication failed. This is usually caused by an incorrect password or missing App Password.\n" +
                 "1. Ensure you are using a 16-character 'App Password' from your Google Account settings (Security -> 2-Step Verification -> App Passwords).\n" +
                 "2. Ensure IMAP is enabled in your Gmail settings: https://mail.google.com/mail/u/0/#settings/fwdandpop\n" +
                 "3. Verify your email address is correct in the settings."
        };
      }
      
      if (attempt >= retryCount) {
        return { success: false, error: `Failed to connect after ${retryCount} attempts: ${errMsg}` };
      }
      const delay = Math.pow(2, attempt) * 1000;
      console.log(`[INGESTION] Retrying in ${delay / 1000}s...`);
      await sleep(delay);
    }
  }

  try {
    const limitRow = await queryOne("SELECT value FROM settings WHERE key = 'email_ingestion_limit'");
    const limit = parseInt(limitRow?.value || '5', 10);

    await connection.openBox('INBOX');

    const searchCriteria = ['UNSEEN', ['FROM', hrEmail]];
    const fetchOptions = { bodies: ['HEADER', 'TEXT', ''], struct: true };

    const messages = await connection.search(searchCriteria, fetchOptions);
    const messagesToProcess = messages.slice(0, limit);

    console.log(`[INGESTION] Found ${messages.length} messages, processing up to ${limit}.`);

    let processedCount = 0;
    for (const message of messagesToProcess) {
      const messageId = message.attributes.uid.toString();
      
      try {
        const processed = await queryOne("SELECT message_id FROM processed_emails WHERE message_id = ?", [messageId]);
        if (processed) {
          console.log(`[INGESTION] Message ${messageId} already processed. Skipping.`);
          continue;
        }

        const all = message.parts.find((part: any) => part.which === '');
        if (!all) {
          console.warn(`[INGESTION] Message ${messageId} has no body part. Skipping.`);
          continue;
        }
        
        const parsed = await simpleParser(all.body);
        const attachments = parsed.attachments || [];
        const processedAttachments = [];

        console.log(`[INGESTION] Processing message ${messageId} from ${parsed.from?.text}. Found ${attachments.length} attachments.`);

        for (const attachment of attachments) {
          const ext = path.extname(attachment.filename || '').toLowerCase();
          if (['.pdf', '.docx'].includes(ext)) {
            const filename = `email_${messageId}_${attachment.filename}`;
            const filepath = path.join(RESUMES_RAW_DIR, filename);
            fs.writeFileSync(filepath, attachment.content);
            
            processedAttachments.push({
              path: filepath,
              type: "resume",
              content: attachment.content,
              ext: ext
            });
          }
        }

        if (processedAttachments.length > 0) {
          const primary = processedAttachments[0];
          await processResumeLogic(primary.path, primary.content, primary.ext, processedAttachments);
          processedCount++;
        }

        await runQuery("INSERT INTO processed_emails (message_id, processed_at) VALUES (?, ?)", [messageId, new Date().toISOString()]);
      } catch (msgError) {
        console.error(`[INGESTION] Failed to process message ${messageId}:`, msgError);
      }
    }

    connection.end();
    await runQuery("UPDATE settings SET value = ? WHERE key = 'last_sync_at'", [new Date().toISOString()]);
    console.log(`[INGESTION] Finished processing. Successfully ingested ${processedCount} resumes.`);
    return { success: true, processedCount };
  } catch (error: any) {
    if (connection) connection.end();
    console.error("Email Ingestion Error during processing:", error);
    return { success: false, error: String(error) };
  }
};
