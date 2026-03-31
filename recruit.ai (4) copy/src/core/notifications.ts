import { WebSocket, WebSocketServer } from 'ws';
import { Server } from 'http';

class NotificationManager {
  private clients: Set<WebSocket> = new Set();

  setup(server: Server) {
    const wss = new WebSocketServer({ server, path: '/ws' });

    wss.on('connection', (ws: WebSocket) => {
      this.clients.add(ws);
      console.log('WebSocket client connected');

      ws.on('close', () => {
        this.clients.delete(ws);
        console.log('WebSocket client disconnected');
      });

      ws.on('error', (error: Error) => {
        console.error('WebSocket error:', error);
        this.clients.delete(ws);
      });
    });
  }

  async broadcast(message: any) {
    const payload = JSON.stringify(message);
    this.clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(payload);
      }
    });
  }
}

export const manager = new NotificationManager();
