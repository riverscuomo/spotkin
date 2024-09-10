import datetime
import os
from server.src.models.models import Ingredient, Job, Token, User
from spotkin_tools.scripts.process_job import process_job as tools_process_job
import time
import spotipy
from flask import jsonify
from server.src.models.models import db
from rich import print


class JobService:
    def __init__(self, data_service, spotify_service):
        self.data_service = data_service
        self.spotify_service = spotify_service

    def add_job(self, user_id, job_data):
        new_job = Job(
            user_id=user_id,
            playlist_id=job_data['playlist_id'],
            name=job_data['name'],
            scheduled_time=job_data.get('scheduled_time'),
            description=job_data.get('description'),
            ban_skits=job_data.get('ban_skits', False)
        )

        for ingredient_data in job_data.get('recipe', []):
            ingredient = Ingredient(
                playlist_id=ingredient_data['source_playlist_id'],
                playlist_name=ingredient_data['source_playlist_name'],
                quantity=ingredient_data['quantity']
            )
            new_job.ingredients.append(ingredient)

        db.session.add(new_job)
        db.session.commit()
        return new_job.to_dict()

    def convert_server_job_to_tools_job(self, job):
        """ Convert a Job model instance to a dictionary that can be used by the original tools script. """
        job_dict = job.to_dict()

        job_dict['playlist_id'] = job_dict['target_playlist']['id']

        for ingredient in job_dict['recipe']:
            ingredient['source_playlist_id'] = ingredient['playlist']['id']
            ingredient['source_playlist_name'] = ingredient['playlist']['name']
        return job_dict
    # Ensure the user exists before creating/updating a job

    def ensure_user_exists(self, user_id):
        user = User.query.filter_by(id=user_id).first()
        if not user:
            # Create user if they don't exist (adjust as necessary for your user fields)
            new_user = User(id=user_id)  # Example
            db.session.add(new_user)
            db.session.commit()

    def get_jobs(self, user_id):
        print(f"Getting jobs for user: {user_id}")
        jobs = Job.query.filter_by(user_id=user_id).all()
        print([job.name for job in jobs])
        return [job.to_dict() for job in jobs]

    def delete_job(self, user_id, job_index):
        self.data_service.delete_job(user_id, job_index)

    def process(self, spotify, job_id, user_id):

        try:

            job = Job.query.filter_by(id=job_id, user_id=user_id).first()

            if not job:
                return jsonify({'status': 'error', 'message': 'Job not found.'}), 404

            job_dict = self.convert_server_job_to_tools_job(job)

            tools_process_job(spotify, job_dict)

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    def process_job(self, job_id, request):
        """ When the user clicks 'Update' in the UI, this function is called to process the job immediately. """

        if 'Authorization' not in request.headers:
            return jsonify({'status': 'error', 'message': 'Authorization header is missing.'}), 401

        access_token = request.headers['Authorization'].split(' ')[1]

        try:
            spotify = spotipy.Spotify(auth=access_token)

            user = spotify.current_user()
            user_id = user['id']

            if token := Token.query.filter_by(user_id=user_id).first():
                token.token_info = {'access_token': access_token}

            else:
                token = Token(user_id=user_id, token_info={
                    'access_token': access_token})
                db.session.add(token)

            db.session.commit()

            result = self.process(spotify, job_id, user_id)

            return jsonify({
                "message": "Processed successfully",
                "status": "success"
            }), 200

        except spotipy.exceptions.SpotifyException as e:
            return jsonify({'status': 'error', 'message': str(e)}), 401

    def process_scheduled_jobs(self):
        print('process_scheduled_jobs...')
        # all_jobs = self.data_service.get_all_data()

        # Get the current UTC hour
        now = datetime.datetime.now(datetime.timezone.utc)
        current_hour = now.hour

        # for user_id, user_data in all_jobs.items():
        jobs = Job.query.all()
        # jobs = user_data.get('jobs', [])
        for job in jobs:

            scheduled_time = job.scheduled_time
            user_id = job.user_id

            if scheduled_time == current_hour:
                # user = User.query.filter_by(id=job.user_id).first()

                print(
                    f"Processing job for user: {user_id} because scheduled time {scheduled_time} matches current hour {current_hour}")
                try:
                    token = Token.query.filter_by(user_id=user_id).first()
                    token_info = token.token_info if token else {}
                    spotify = self.spotify_service.create_spotify_client(
                        token_info)

                    result = self.process(spotify, job, user_id)

                    job.last_autorun = now.timestamp()
                    db.session.commit()
                    print(
                        f"Job processed successfully for user: {user_id}")

                except Exception as e:
                    print(
                        f"Error processing job for user {user_id}: {str(e)}")
            else:
                print(
                    f"Skipping job for user: {job.user_id} because scheduled time {scheduled_time} does not match current hour {current_hour}")

    def get_schedule(self):
        all_jobs = self.data_service.get_all_data()
        schedule_info = {
            user_id: {
                'jobs': [{
                    'name': job.get('name', 'Unnamed job'),
                    'scheduled_time': job['scheduled_time'],
                    'last_processed': job.get('last_processed', 'Never'),
                } for job in user_data.get('jobs', [])]
            } for user_id, user_data in all_jobs.items()
        }
        return jsonify({"status": "success", "schedule": schedule_info})

    def update_job(self, job_id, updated_job_data, user_id):
        print(f"Updating job {job_id} for user {user_id}")
        # ensure the user is in the db
        self.ensure_user_exists(user_id)
        # Try to find the existing job by job_id and user_id
        job = Job.query.filter_by(id=job_id, user_id=user_id).first()

        if job:
            # Update the existing job with new data
            for key, value in updated_job_data.items():
                if hasattr(job, key):
                    if key == 'recipe':
                        # Handle the 'recipe' separately since it's a relationship
                        job.recipe = []  # Clear existing ingredients

                        # Use a set to track playlist IDs for preventing duplicate ingredients
                        added_playlists = set()

                        for ingredient_data in value:
                            ingredient = Ingredient.from_dict(ingredient_data)
                            # Use the playlist id to determine uniqueness
                            playlist_id = ingredient.playlist.get('id')

                            if playlist_id not in added_playlists:
                                job.recipe.append(ingredient)
                                added_playlists.add(playlist_id)
                                # Update the last_updated timestamp
                                job.last_updated = int(time.time())
                            else:
                                print(
                                    f"Duplicate playlist detected: {playlist_id}, skipping.")
                    else:
                        # Update scalar attributes
                        setattr(job, key, value)
                else:
                    print(f"Server Job model does not have attribute: {key}")
        else:
            # Create a new job if it doesn't exist
            job = Job.from_dict(updated_job_data)
            job.id = job_id  # Assign the provided job_id
            job.user_id = user_id  # Ensure the job is linked to the correct user
            # Update the last_updated timestamp
            job.last_updated = int(time.time())
            db.session.add(job)

        db.session.commit()  # Commit the changes to the database
        return job.to_dict()  # Return the job as a dictionary

    def update_job_schedule(self, data):
        user_id = data['user_id']
        new_time = data['new_time']
        job_name = data.get('job_name', None)

        all_jobs = self.data_service.get_all_data()
        if user_id in all_jobs:
            for job in all_jobs[user_id]['jobs']:
                if job_name is None or job['name'] == job_name:
                    job['scheduled_time'] = new_time
            self.data_service.store_job_and_token(
                user_id, all_jobs[user_id]['jobs'], all_jobs[user_id]['token'])
            return jsonify({"status": "updated", "new_time": new_time})
        else:
            return jsonify({"status": "error", "message": "User not found"}), 404
