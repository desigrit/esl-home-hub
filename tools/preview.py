"""Preview only. Reuses the existing backend and never starts another scheduler."""
from ronhub import create_app
app = create_app()
try:
    from esl_note_proxy import register_note_controller
    register_note_controller(app)
except ImportError:
    pass
app.run(host='0.0.0.0', port=5010, debug=False)
