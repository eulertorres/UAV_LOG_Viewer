import http.server
import socketserver
import threading
import tempfile
import os

class MapServer:
    """
    Gerencia um servidor HTTP simples em uma thread separada para servir
    os arquivos HTML do mapa Folium.
    """
    def __init__(self, port=8000):
        self.port = port
        self.temp_dir = tempfile.mkdtemp()
        self.httpd = None
        self.server_thread = None

    def start(self):
        if self.server_thread and self.server_thread.is_alive():
            print("Servidor já está rodando.")
            return
            
        # Tenta encontrar uma porta livre se a padrão estiver em uso
        while True:
            try:
                Handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(*args, directory=self.temp_dir, **kwargs)
                self.httpd = socketserver.TCPServer(("", self.port), Handler)
                break
            except OSError:
                print(f"Porta {self.port} em uso. Tentando a próxima...")
                self.port += 1

        self.server_thread = threading.Thread(target=self.httpd.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
        print(f"Servidor local iniciado em http://127.0.0.1:{self.port} servindo de {self.temp_dir}")

    def stop(self):
        if self.httpd:
            print("Desligando o servidor...")
            self.httpd.shutdown()
            self.httpd.server_close()
            # Limpa o diretório temporário
            for filename in os.listdir(self.temp_dir):
                os.remove(os.path.join(self.temp_dir, filename))
            os.rmdir(self.temp_dir)
            print("Servidor desligado e arquivos temporários limpos.")

    def get_temp_dir(self):
        return self.temp_dir
    
    def get_port(self):
        return self.port