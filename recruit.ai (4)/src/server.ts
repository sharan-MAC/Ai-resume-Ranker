import express, { Request, Response } from 'express';
import path from 'path';
import fs from 'fs';
import cors from 'cors';
import { createServer } from 'http';
import { initDb } from './db/session';
import apiRouter from './api/endpoints';
import { manager } from './core/notifications';
import { performIngestion } from './services/emailService';

const app = express();
const server = createServer(app);
const PORT = 3000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// WebSocket
manager.setup(server);

// API Routes
app.use('/api', apiRouter);

// Static Files
const resumesDir = path.join(process.cwd(), 'resumes_raw');
if (!fs.existsSync(resumesDir)) {
  fs.mkdirSync(resumesDir);
}
app.use('/resumes_raw', express.static(resumesDir));

const uploadsDir = path.join(process.cwd(), 'uploads');
if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir);
}

// Serve Frontend
// The original app used Jinja2 for index.html in /templates
app.get('/', (req: Request, res: Response) => {
  res.sendFile(path.join(process.cwd(), 'templates', 'index.html'));
});

// SPA Fallback
app.use((req: Request, res: Response) => {
  if (req.path.startsWith('/api')) {
    return res.status(404).json({ error: 'API route not found' });
  }
  res.sendFile(path.join(process.cwd(), 'templates', 'index.html'));
});

// Background Worker
const startWorker = () => {
  console.log("Starting background ingestion worker...");
  setInterval(async () => {
    try {
      await performIngestion();
    } catch (error) {
      console.error("Background Ingestion Error:", error);
    }
  }, 60000);
};

// Global Error Handler
app.use((err: any, req: Request, res: Response, next: any) => {
  console.error("Unhandled Server Error:", err);
  res.status(500).json({ error: "Internal server error" });
});

// Start Server
const start = async () => {
  console.log("Initializing Database...");
  try {
    await initDb();
  } catch (error) {
    console.error("Database Initialization Failed:", error);
  }

  startWorker();

  server.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
};

start();
