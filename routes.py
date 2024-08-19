
from flask import jsonify, request


def register_routes(app, job_service):
    @app.route('/process_job', methods=['POST'])
    def process_job_api():
        return job_service.process_job(request)

    @app.route('/refresh_jobs', methods=['POST'])
    def refresh_jobs():
        job_service.process_scheduled_jobs()
        return jsonify({"status": "processing complete"})

    @app.route('/get_schedule', methods=['GET'])
    def get_schedule():
        return job_service.get_schedule()

    @app.route('/update_job_schedule', methods=['POST'])
    def update_job_schedule():
        return job_service.update_job_schedule(request.json)

    @app.route('/')
    def home():
        return 'Home - Go to /spotify-login to login with Spotify.'