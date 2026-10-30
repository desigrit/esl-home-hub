import argparse
from ronhub import create_app

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5173)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    app = create_app()
    from waitress import serve
    serve(app, host=args.host, port=args.port, threads=8)
