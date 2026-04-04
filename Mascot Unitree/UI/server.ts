import express from 'express';
import { createServer as createViteServer } from 'vite';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json({ limit: '50mb' }));

  app.post('/api/generate', (req, res) => {
    const { prompt, persona } = req.body;

    const pythonProcess = spawn('python3', [path.join(__dirname, 'process_backend.py')]);
    
    let dataString = '';
    let errorString = '';

    pythonProcess.stdout.on('data', (data) => {
      dataString += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      errorString += data.toString();
    });

    pythonProcess.on('close', (code) => {
      if (code !== 0) {
        console.error('Python script exited with code', code);
        console.error(errorString);
        return res.status(500).json({ error: 'Failed to process request', details: errorString });
      }
      
      try {
        const result = JSON.parse(dataString);
        res.json(result);
      } catch (e) {
        console.error('Failed to parse python output:', dataString);
        res.status(500).json({ error: 'Invalid response from backend' });
      }
    });

    pythonProcess.stdin.write(JSON.stringify({ prompt, persona }));
    pythonProcess.stdin.end();
  });

  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.join(__dirname, 'dist')));
    app.get('*', (req, res) => {
      res.sendFile(path.join(__dirname, 'dist', 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
