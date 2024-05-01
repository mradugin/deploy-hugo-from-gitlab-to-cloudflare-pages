import os
import requests
from datetime import datetime, timedelta, UTC
from dateutil.parser import parse
import argparse

def get_environment_variables():
    api_token = os.getenv('CLOUDFLARE_API_TOKEN')
    account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
    project_name = os.getenv('CLOUDFLARE_PROJECT_NAME')
    if not (api_token and account_id and project_name):
        print('Missing environment variables. Please make sure to set CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, and CLOUDFLARE_PROJECT_NAME.')
        exit(1)
    return api_token, account_id, project_name

def get_page_deployments(environment, api_token, account_id, project_name):
    page = 1
    all_deployments = []

    while True:
        try:
            response = requests.get(
                f'https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{project_name}/deployments',
                headers={'Authorization': f'Bearer {api_token}'},
                params={'page': page, 'per_page': 20}  # Adjust per_page as needed
            )
            response_data = response.json()

            if 'result' not in response_data:
                break

            result = response_data['result']
            all_deployments.extend(result)

            # If there are more pages, fetch the next page
            if response_data['result_info']['page'] < response_data['result_info']['total_pages']:
                page += 1
            else:
                break  # Exit loop if all pages are fetched
        except requests.exceptions.RequestException as e:
            handle_api_error(e)
            break

    return [deployment for deployment in all_deployments if deployment['environment'] == environment]

def is_latest_production_page_deployment(deployment):
    return deployment['environment'] == 'production' and deployment['aliases'] is not None and len(deployment['aliases']) > 0

def delete_page_deployment(deployment_id, api_token, account_id, project_name):
    try:
        requests.delete(
            f'https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/{project_name}/deployments/{deployment_id}',
            headers={'Authorization': f'Bearer {api_token}'},
            params={'force': True}
        )
        print(f'Page deployment with ID {deployment_id} has been deleted.')
    except requests.exceptions.RequestException as e:
        handle_api_error(e)

def handle_api_error(error):
    if error.response:
        print(f'API responded with status {error.response.status_code}:', error.response.text)
    elif error.request:
        print('No response received:', error)
    else:
        print('Error setting up the request:', error)

def main():
    parser = argparse.ArgumentParser(description='Fetch and delete obsolete page deployments')
    parser.add_argument('--environment', choices=['production', 'preview'], required=True, help='deployment environment')
    parser.add_argument('--count', type=int, required=True, help='number of deployments to keep')
    parser.add_argument('--days', type=int, required=True, help='number of days to keep')
    parser.add_argument('--dry-run', action='store_true', help='perform a dry run')
    args = parser.parse_args()

    api_token, account_id, project_name = get_environment_variables()
    environment = args.environment
    count_threshold = args.count
    days_threshold = args.days
    date_threshold = timedelta(days=days_threshold)
    is_dry_run = args.dry_run

    print(f'Fetching all {environment} page deployments...')
    page_deployments = get_page_deployments(environment, api_token, account_id, project_name)
    print(f'Found {len(page_deployments)} {environment} page deployments.')

    if not page_deployments:
        print(f'No {environment} page deployments found.')
        return
    
    page_deployments = sorted(page_deployments, key=lambda deployment: deployment['created_on'], reverse=True)

    print(f'Deleting obsolete {environment} page deployments older than {days_threshold} days, while keeping {count_threshold} latest...')
    current_date = datetime.now(UTC)
    deleted_count = 0
    keep_count = 0
    for deployment in page_deployments:
        deployment_date = parse(deployment['created_on'])
        if deployment_date < current_date - date_threshold:
            print(f"Deployment ID: {deployment['id']}, created on: {deployment['created_on']}, url: {deployment['url']}, aliases: {deployment['aliases']}")
            if keep_count < count_threshold:
                print(f'Latest {keep_count + 1} page deployment has been kept.')
                keep_count += 1
                continue
            if is_latest_production_page_deployment(deployment):
                print(f'Page deployment for latest production environment has been skipped.')
                continue
            if is_dry_run:
                print(f'Page deployment for deletion, but has been skipped due to dry run.')
                continue
            delete_page_deployment(deployment['id'], api_token, account_id, project_name)
            deleted_count += 1

    print(f'{deleted_count} obsolete {environment} page deployments have been deleted.')

if __name__ == "__main__":
    main()
