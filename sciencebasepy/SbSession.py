"""This Python module provides some basic services for interacting with ScienceBase."""
from __future__ import print_function

# For Python 3.0 and later
import http.client as httplib
from urllib.parse import urlencode
import urllib.parse as urlparse
import sys
import logging
import json
import os
import getpass
import requests
import hashlib
import time

from pkg_resources import get_distribution
from pkg_resources import DistributionNotFound
from sb3.SbSessionEx import SbSessionEx
from sb3 import client

class SbSession:
    """SbSession encapsulates a session with ScienceBase, and provides methods for working with
    ScienceBase Catalog Items.
    """
    _base_sb_url = None
    _base_item_url = None
    _base_items_url = None
    _base_upload_file_url = None
    _base_item_link_url = None
    _base_upload_file_temp_url = None
    _base_download_files_url = None
    _base_move_item_url = None
    _base_undelete_item_url = None
    _base_shortcut_item_url = None
    _base_unlink_item_url = None
    _base_directory_url = None
    _base_person_url = None
    _users_id = None
    _username = None
    _jossosessionid = None
    _session = None
    _retry = False
    _max_item_count = 1000
    _env = None
    _sbSessionEx = None
    _refresh_time_limit = 600

    def __init__(self, env=None):
        """Initialize session and set JSON headers"""
        self._env = env
        if env == 'beta':
            self._base_sb_url = "https://beta.sciencebase.gov/catalog/"
            self._base_directory_url = "https://beta.sciencebase.gov/directory/"
            self._users_id = "4f4e4772e4b07f02db47e231"
            self._sb_manager_url = "https://beta.staging.sciencebase.gov/manager/"
            # self._sb_manager_url = 'http://localhost:3000/manager'
        elif env == 'dev':
            self._base_sb_url = "http://localhost:8090/catalog/"
            self._base_directory_url = "https://beta.sciencebase.gov/directory/"
            self._sb_manager_url = "https://dev.staging.sciencebase.gov/manager/"
        else:
            self._base_sb_url = "https://www.sciencebase.gov/catalog/"
            self._base_directory_url = "https://www.sciencebase.gov/directory/"
            self._users_id = "4f4e4772e4b07f02db47e231"
            self._sb_manager_url = "https://sciencebase.usgs.gov/manager/"

        self._base_item_url = self._base_sb_url + "item/"
        self._base_items_url = self._base_sb_url + "items/"
        self._base_upload_file_url = self._base_sb_url + "file/uploadAndUpsertItem/"
        self._base_download_files_url = self._base_sb_url + "file/get/"
        self._base_upload_file_temp_url = self._base_sb_url + "file/upload/"
        self._base_item_link_url = self._base_sb_url + "itemLink/"
        self._base_move_item_url = self._base_items_url + "move/"
        self._base_undelete_item_url = self._base_item_url + "undelete/"
        self._base_shortcut_item_url = self._base_items_url + "addLink/"
        self._base_unlink_item_url = self._base_items_url + "unlink/"
        self._base_person_url = self._base_directory_url + "person/"

        self._session = requests.Session()
        self._session.headers.update({'Accept': 'application/json'})
        sciencebasepy_agent = ' sciencebase-sciencebasepy'
        try:
            sciencebasepy_agent += f'/{get_distribution("sciencebasepy").version}'
        except DistributionNotFound:
            pass
        self._session.headers.update({'User-Agent': self._session.headers['User-Agent'] + sciencebasepy_agent})

    def get_token(self):
        """Convenience function to help users in obtaining a token for authentication.

        Opens SB manager in the default system browser and 
        prints instructions for copying and using the token
        """
        print("A browser window/tab should momentarily open with ScienceBase Manager")
        print("Sign in using active directory or login.gov")
        print("Click the user icon in the upper right and select 'Copy API token'")
        print("This copies the token to your clipboard")
        print("Use this value in the add_token function as the token_json parameter")
        time.sleep(4)
        import webbrowser
        webbrowser.open(self._sb_manager_url, new=1, autoraise=True)

    def add_token(self, token_json):
        """Add Keycloak access token for authentication

        :param token_json: json object obtained from "Copy API Key" button in ScienceBase Manager
        """
        self._sbSessionEx = SbSessionEx(self._env)
        self._sbSessionEx.add_token(token_json=token_json)
        self._update_headers_keycloak()

        self._last_token_update = time.time()

    def refresh_token(self, refresh_time_limit=None):
        """ Force refresh the access and refresh tokens

        :param refresh_time_limit: The time limit in seconds before the token expires to refresh the token
        """
        if refresh_time_limit is None:
            # No time limit specified, force refresh the token
            self._sbSessionEx.refresh_token() 
        else:
            # Time limit specified, refresh the token only if it's going to expire within the time limit
            self._sbSessionEx.refresh_token_before_expire(time_remaining=refresh_time_limit)
        self._update_headers_keycloak()

    def _refresh_check(self):
        """Refresh our Keycloak token if it's going to expire within 10 min
        """
        if self._sbSessionEx is None:
            return False
        else:
            try:
                return self.refresh_token(refresh_time_limit=self._refresh_time_limit)
            except:
                return False
        return True

    def login(self, username, password):
        """Log into ScienceBase

        :param username: The ScienceBase user to log in as
        :param password: The ScienceBase password for the given user
        :return: The SbSession object with the user logged in
        """
        # Login to Keycloak for SB3 calls
        self._username = username
        self._sbSessionEx = SbSessionEx(self._env).login(username, password)
        self._update_headers_keycloak()

        return self
    
    def _update_headers_keycloak(self):
        """Updates the session's headers with the keycloak authorization headers
        """
        self._session.headers.update({'accept': 'application/json'})
        self._session.headers.update({'authorization': 'Bearer ' + self._sbSessionEx.get_access_token()})

    def logout(self):
        """Log out of ScienceBase by revoking the Keycloak tokens"""
        if self._sbSessionEx.revoke_token():
            # Reset the session
            self._session = requests.Session()
            self._session.headers.update({'Accept': 'application/json'})
            sciencebasepy_agent = ' sciencebase-sciencebasepy'
            try:
                sciencebasepy_agent += f'/{get_distribution("sciencebasepy").version}'
            except DistributionNotFound:
                pass
            self._session.headers.update({'User-Agent': self._session.headers['User-Agent'] + sciencebasepy_agent})
            # Print out message
            print ('You have now been logged out.')

    def loginc(self, username, tries=3):
        """Log into ScienceBase, prompting for the password
        
        :param username: The ScienceBase user to log in as
        :return: The SbSession object with the user logged in
        """
        while tries > 0:
            password = getpass.getpass('Active Directory password')
            try:
                return self.login(username, password)
            except Exception:
                tries -= 1
                print("Invalid password, try again")
        raise Exception("Too many invalid password attemps")

    def is_logged_in(self):
        """Determine whether the SbSession is logged in and active in ScienceBase
        
        :return: Whether the SbSession is logged in and active in ScienceBase.
        """
        if self._sbSessionEx is None:
            return False
        else:
            return self._sbSessionEx.is_logged_in()

    def ping(self):
        """Ping ScienceBase.  A very low-cost operation to determine whether ScienceBase is available.
        
        :return: JSON response from ScienceBase Catalog
        """
        return self.get_json(self._base_item_url + 'ping')

    def get_session_info(self):
        """Get the JOSSO session information for the current session

        :return: ScienceBase Josso session info
        """
        return self.get_json(self._base_sb_url + 'jossoHelper/sessionInfo?includeJossoSessionId=true')

    def get_item(self, itemid, params=None):
        """Get the ScienceBase Item JSON with the given ID
        
        :param params: Allows you to specify query params, such as {'fields':'title,ancestors'} for ?fields=title,ancestors
        :return: JSON for the ScienceBase Item with the given ID
        """
        self._refresh_check()
        ret = self._session.get(self._base_item_url + itemid, params=params)
        return self._get_json(ret)

    def get_hidden_properties(self, item_id):
        """Get the list of all hidden properties for a ScienceBase Item

        :param item_id: ID of the ScienceBase Item
        :return: JSON for the ScienceBase Item with the given ID
        """
        self._refresh_check()
        ret = self._session.get(self._base_item_url + item_id + '/hiddenProperties')
        return self._get_json(ret)

    def get_hidden_property(self, item_id, hidden_property_id):
        """Get the ScienceBase hidden property JSON with the given item and Hidden Property ID

        :param item_id: ID of the ScienceBase Item
        :param hidden_property_id: ID of hidden property
        :return: JSON for the ScienceBase Item's Hidden Property with the given ID
        """
        self._refresh_check()
        ret = self._session.get(self._base_item_url + item_id + '/hiddenProperties/' + hidden_property_id)
        return self._get_json(ret)

    def find_hidden_property(self, hidden_property):
        """Find ScienceBase Items by hidden property value
        
        :param hidden_property: ScienceBase Item Hidden Property JSON: {"type": ..., "value": ...}
        :return: Item Hidden Property JSON containing the first page of matching ScienceBase Items. Use the next() method for
        subsequent pages.
        """
        self._refresh_check()
        ret = {}
        if hidden_property:
            params = {"max": 1000}
            if "type" in hidden_property:
                params["type"] = hidden_property["type"]
            if "value" in hidden_property:
                params["value"] = hidden_property["value"]
            ret = self.get_json(self._base_sb_url + "itemHiddenProperties", params = params)
        return ret
        
    def find_items_by_filter_and_hidden_property(self, params, hidden_property):
        """Search for ScienceBase items by filter and hidden property

        Warning: Because of the way hidden property results must be joined to ScienceBase Catalog search results,
        this method returns all matching items. Queries returning too many items may be blocked by ScienceBase.

        :param params: ScienceBase Catalog search parameters
        :param hidden_property: ScienceBase Item Hidden Property JSON: {"type": ..., "value": ...}
        :return: ScienceBase Catalog search response object containing the first page of results for the search
        """
        #
        # Retrieve all of the hidden property results 
        #
        self._refresh_check()
        ret = []
        properties = []
        
        response = self.find_hidden_property(hidden_property)
        while response and "itemHiddenProperties" in response:
            for item_hidden_property in response["itemHiddenProperties"]:
                properties.append(item_hidden_property)
            response = self.next(response)
        #
        # Save a list of all the ScienceBase Item IDs found, and map properties to their item
        #
        ids = []
        item_props = {}
        for prop in properties:
            ids.append(prop["itemId"])
            item_props[prop["itemId"]] = {prop["type"]: prop["value"]}
        #
        # Now perform the ScienceBase Item search part of the query, saving only Items whose
        # ID is in the list of matching hidden property items
        #
        response = self.find_items(params)
        while response and "items" in response and response["items"]:
            for item in response["items"]:
                if item["id"] in ids:
                    item["hiddenProperties"] = item_props[item["id"]]
                    ret.append(item)
            response = self.next(response)
        return ret

    def get_item_ids_by_hidden_property(self, hidden_property):
        """Get the ScienceBase IDs of Items associated with the given hidden property
        
        :param hidden_property: ScienceBase Item Hidden Property JSON: {"type": ..., "value": ...}
        :return: List of ScienceBase Item IDs containing the given hidden property
        """
        self._refresh_check()
        ret = []
        for item_hidden_property in self.find_hidden_property(hidden_property):
            ret.append(item_hidden_property["itemId"])
        return ret

    def create_item(self, item_json):
        """Create a new Item in ScienceBase

        :param item_json: JSON representing the ScienceBase Catalog item to create
        :return: Full item JSON from ScienceBase Catalog after creation
        """
        self._refresh_check()
        ret = self._session.post(self._base_item_url, data=json.dumps(item_json))
        return self._get_json(ret)

    def create_items(self, items_json):
        """Create new Items in ScienceBase

        :param items_json: JSON list representing the ScienceBase Catalog items to create
        :return: Full items JSON from ScienceBase Catalog after creation
        """
        self._refresh_check()
        ret = self._session.post(self._base_items_url + "upsert/", data=json.dumps(items_json))
        return self._get_json(ret)

    def create_hidden_property(self, item_id, hidden_property_json):
        """Create a new Hidden Property for an Item in ScienceBase

        :param item_id: ID of the ScienceBase Item to create a hidden property for
        :param hidden_property_json: data (for the JSON) representing the hidden property to create
        :return: JSON of hidden property after creation
        """
        self._refresh_check()
        ret = self._session.post(self._base_item_url + item_id + '/hiddenProperties/', data=json.dumps(hidden_property_json))
        return self._get_json(ret)

    def update_item(self, item_json):
        """Update an existing ScienceBase Item

        :param item_json: JSON representing the ScienceBase Catalog item to update
        :return: Full item JSON from ScienceBase Catalog after update
        """
        self._refresh_check()
        ret = self._session.put(self._base_item_url + item_json['id'], data=json.dumps(item_json))
        return self._get_json(ret)

    def update_hidden_property(self, item_id, hidden_property_id, hidden_property_json):
        """Update an existing hidden property of a ScienceBase Item

        :param item_id: ID of the ScienceBase Item
        :param hidden_property_id: ID of hidden property
        :param hidden_property_json: data for updated hidden property
        :return: Full item JSON from ScienceBase Catalog after update
        """
        self._refresh_check()
        ret = self._session.put(self._base_item_url + item_id + '/hiddenProperties/' + hidden_property_id, data=json.dumps(hidden_property_json))
        return self._get_json(ret)

    def update_items(self, items_json):
        """Update multiple ScienceBase items

        :param items_json: List of ScienceBase Catalog Item JSON to update
        :return: ScienceBase JSON response
        """
        self._refresh_check()
        ret = self._session.put(self._base_items_url, data=json.dumps(items_json))
        return self._get_json(ret)

    def delete_item(self, item_json):
        """Delete an existing ScienceBase Item

        :param item_json: JSON representing the ScienceBase Catalog item to delete
        :return: True if the item was successfully deleted
        """
        self._refresh_check()
        return self._sbSessionEx.delete_item(item_json['id']) 

    def delete_hidden_property(self, item_id, hidden_property_id):
        """Delete an existing Hidden Property from a ScienceBase Item

        :param item_id: ID of the ScienceBase Item
        :param hidden_property_id: ID of hidden property
        :return: True if the item was successfully deleted
        """
        self._refresh_check()
        ret = self._session.delete(self._base_item_url + item_id + '/hiddenProperties/' + hidden_property_id)
        self._check_errors(ret)
        return True

    def undelete_item(self, itemid):
        """Undelete a ScienceBase Item
        :param itemid: ID of the Item to undelete
        :return: JSON of the undeleted Item
        """
        self._refresh_check()
        ret = self._session.post(self._base_undelete_item_url, params={'itemId': itemid})
        self._check_errors(ret)
        return self._get_json(ret)

    def delete_items(self, itemIds):
        """Delete multiple ScienceBase Items.  This is much more efficient than using delete_item() for mass
        deletions, as it performs it server-side in one call to ScienceBase.
        
        :param itemIds: List of Item IDs to delete
        :return: True if the items were successfully deleted
        """
        self._refresh_check()
        for i in range(0, len(itemIds), self._max_item_count):
            ids_json = []
            for itemId in itemIds[i:i + self._max_item_count]:
                ids_json.append({'id': itemId})
            ret = self._session.delete(self._base_items_url, data=json.dumps(ids_json))
            self._check_errors(ret)
        return True

    def move_item(self, itemid, parentid):
        """Move an existing ScienceBase Item under a new parent

        :param itemid: ID of the Item to move
        :param parentid: ID of the new parent Item
        :return: The JSON of the moved Item
        """
        self._refresh_check()
        ret = self._session.post(self._base_move_item_url, params={'itemId': itemid, 'destId': parentid})
        self._check_errors(ret)
        return self._get_json(ret)

    def move_items(self, itemids, parentid):
        """Move ScienceBase Items under a new parent

        :param itemids: A list of ScienceBase Catalog Item IDs of the Items to move
        :param parentid: ScienceBase Catalog Item ID of the new parent Item
        :return: A count of the number of Items moved
        """
        self._refresh_check()
        count = 0
        if itemids:
            for itemid in itemids:
                print('moving ' + itemid)
                self.move_item(itemid, parentid)
                count += 1
        return count

    def upload_file_to_item(self, item, filename, scrape_file=True):
        """Upload a file to an existing Item in ScienceBase

        :param item: ScienceBase Catalog Item JSON of the Item to update
        :param filename: Filenames of the file to upload
        :param scrape_file: Whether to scrape metadata and create extensions from special files
        :return: The ScienceBase Catalog Item JSON of the updated Item
        """
        return self.upload_files_and_update_item(item, [filename], scrape_file)

    def upload_s3_files(self, itemid, s3_path, filenames):
        """Upload a list of files from an external S3 bucket to an existing Item in ScienceBase

        :param itemid: ScienceBase Catalog Item ID of the item to update
        :param s3_path: External S3 bucket path, e.g. s3://mys3bucket/12 where files to be uploaded are located
        :param filenames: List of filenames in external S3 bucket, located under s3_path, to be uploaded to Item
        """
        if not self._sbSessionEx.is_logged_in():
            print(f'{self._username} not logged into Keycloak -- cloud services not available')
        else:
            try:
                self.get_item(itemid)

                input = {"filelist": filenames, "id": itemid, "key": s3_path, "username": self._username}

                response = self._sbSessionEx.upload_s3_files(input)

                if response:
                    print("Triggered upload of S3 files to ScienceBase Item")
                else:
                    print("Error uploading S3 files to ScienceBase Item")
            except Exception:
                print("Error triggering upload of S3 files to ScienceBase Item")

    def upload_cloud_file_to_item(self, itemid, filename):
        """Upload a file to cloud storage on an existing Item in ScienceBase

        :param itemid: ScienceBase Catalog Item ID of the Item to update
        :param filename: Filenames of the file to upload
        :return: The ScienceBase Catalog Item JSON of the updated Item
        """
        ret = None
        if not self._sbSessionEx.is_logged_in():
            print(f'{self._username} not logged into Keycloak -- cloud services not available')
        else:
            response = self._sbSessionEx.upload_cloud_file_upload_session(itemid, filename)
            if 'data' in response and 'completeMultiPartUpload' in response['data'] and 'Successful' in response['data']['completeMultiPartUpload']:
                just_fname = os.path.split(filename)[1]
                path_on_disk = ""
                while path_on_disk == "":
                    ret = self.get_item(itemid)
                    time.sleep(3)
                    print("Completing upload...Please wait.")
                    if 'files' in ret:
                        for f in ret['files']:
                            if 'name' in f:
                                if f['name'] == just_fname:
                                    if 'pathOnDisk' in f:
                                        path_on_disk = f['pathOnDisk']
            else:
                raise Exception('Cloud upload failed for', filename)
        return ret

    def scrape_S3_fgdc_xml(self, itemid, filename):
        """
        Executes a GraphQL mutation to convert FGDC XML metadata into ScienceBase JSON.

        This function sends a mutation request to the ScienceBase GraphQL API using the provided metadata input and
        session context. It's typically used to ingest or update metadata stored in S3 into a ScienceBase item.

        Parameters:
            input (dict): Mutation payload with keys:
                - action (str): Operation type (e.g., 'update_item')
                - bucket (str): Name of the S3 bucket containing the FGDC XML file
                - fileName (str): The target filename to process
                - fileType (str): MIME type of the FGDC file (e.g., 'application/fgdc+xml')
                - itemId (str): ScienceBase item ID to update
                - pathOnDisk(str): __s3__
            sb_session_ex (SbSessionEx): Authenticated ScienceBase session object providing headers, endpoint URL,
                and a logger for diagnostics.

        Returns:
            str: Raw response text from the ScienceBase GraphQL endpoint, typically containing the item ID or status.

        Raises:
            Exception: If the HTTP response status is not 200 or if GraphQL errors are returned.

        Example:
            >>> input = {
            >>>     'action': 'update_item',
            >>>     'bucket': 'my-s3-bucket',
            >>>     'fileName': 'metadata.xml',
            >>>     'fileType': 'application/fgdc+xml',
            >>>     'itemId': '123abc',
            >>>     'pathOnDisk': '__s3__'
            >>> }
            >>> scrape_fgdc_xml(input, sb_session_ex)
        """
        if not self._sbSessionEx.is_logged_in():
            print(f'{self._username} not logged into Keycloak -- cloud services not available')
            return False
        
        item = self.get_item(itemid)
        files = item.get('files', {})
        file_match = next((item for item in files if item['name'] == filename), None)
        if not file_match:
            print(f"{filename} not found in item's files")
            return False
        bucket = file_match.get('bucket', None)
        if not bucket:
            print(f"bucket not found in file's json")
            return False
        content_type = file_match.get('contentType', '')
        if not content_type == 'application/fgdc+xml':
            print(f"{filename} not of type 'application/fgdc+xml'")
            return False
        path_on_disk = '__s3__'

        response = self._sbSessionEx.scrape_fgdc_xml(itemid, filename, bucket, content_type, path_on_disk)
        return response

    def generate_S3_download_links(self, itemid, filenames):
        """generate list of bulk cloud file download tokens

        :param itemid: ScienceBase Catalog Item ID of the Item
        :param filenames: Filenames of the files to download
        :return: List of tokenized S3 download links
        """
        download_links = []

        if not self._sbSessionEx.is_logged_in():
            print(f'{self._username} not logged into Keycloak -- cloud services not available')
        else:
            item = self.get_item(itemid)
            selected_rows = []

            for filename in filenames:
                cuid = ""
                key = ""
                title = ""
                useForPreview = False

                if 'files' in item:
                    for f in item['files']:
                        if 'name' in f:
                            if f['name'] == filename:
                                if 'cuid' in f:
                                    cuid = f['cuid']
                                if 'key' in f:
                                    key = f['key']
                                if 'title' in f:
                                    title = f['title']
                                if 'useForPreview' in f:
                                    useForPreview = f['useForPreview']
                                break

                if cuid == "":
                    if 'facets' in item:
                        for facet in item['facets']:
                            if 'files' in facet:
                                for f in facet['files']:
                                    if f['name'] == filename:
                                        if 'cuid' in f:
                                            cuid = f['cuid']
                                        if 'key' in f:
                                            key = f['key']
                                        if 'title' in f:
                                            title = f['title']
                                        if 'useForPreview' in f:
                                            useForPreview = f['useForPreview']
                                        break

                selected_row = {'cuid': cuid, 'key': key, 'title': title, 'useForPreview': useForPreview}

                if cuid is None:
                    raise Exception('On-premise file detected: ' + filename)

                selected_rows.append(selected_row)

            for i in range(0, len(selected_rows), 10):
                chunk = selected_rows[i:i+10]
                response = self._sbSessionEx.bulk_cloud_download(chunk)
                if response:
                    for uri in response['data']['getS3DownloadUrl']:
                        download_links.append(uri['downloadUri'])
                else:
                    raise Exception('Tokenized S3 link generation failed for ' + itemid)
        return download_links

    def download_cloud_files(self, filenames, download_links, destination='.'):
        """download list of ScienceBase files using tokenized S3 download links
        :param filenames: Filenames of the files to download
        :param download_links: List of tokenized S3 download links
        :param destination: Local destination where files are to be downloaded
        """
        if len(filenames) != len(download_links):
            raise Exception('Error: number of filenames not consistent with number of download links')

        for i in range(len(download_links)):
            filename = filenames[i]
            link = download_links[i]
            self.download_file(link, filename, destination, False, True)

    def upload_file_and_create_item(self, parentid, filename, scrape_file=True):
        """Upload a file and create a new Item in ScienceBase

        :param parentid: ScienceBase Catalog Item JSON of the Item under which to create the new Item
        :param filename: Filename of the file to upload
        :param scrape_file: Whether to scrape metadata and create extensions from special files
        :return: The ScienceBase Catalog Item JSON of the new Item
        """
        return self.upload_files_and_create_item(parentid, [filename], scrape_file)    

    def upload_files_and_create_item(self, parentid, filenames, scrape_file=True):
        """Upload multiple files and create a new Item in ScienceBase

        :param parentid: ScienceBase Catalog Item JSON of the Item under which to create the new Item
        :param filenames: Filename of the files to upload
        :param scrape_file: Whether to scrape metadata and create extensions from special files
        :return: The ScienceBase Catalog Item JSON of the new Item
        """
        return self.upload_files_and_upsert_item({'parentId': parentid}, filenames, scrape_file)

    def upload_files_and_update_item(self, item, filenames, scrape_file=True):
        """Upload multiple files and update an existing Item in ScienceBase

        :param item: ScienceBase Catalog Item JSON of the Item to update
        :param filenames: Filenames of the files to upload
        :param scrape_file: Whether to scrape metadata and create extensions from special files
        :return: The ScienceBase Catalog Item JSON of the updated Item
        """
        return self.upload_files_and_upsert_item(item, filenames, scrape_file)

    def upload_files_and_upsert_item(self, item, filenames, scrape_file=True):
        """Upload multiple files and create or update an Item in ScienceBase

        :param item: ScienceBase Catalog Item JSON of the Item to update
        :param filenames: Filenames of the files to upload
        :param scrape_file: Whether to scrape metadata and create extensions from special files
        :return: The ScienceBase Catalog Item JSON of the updated Item
        """
        self._refresh_check()
        url = self._base_upload_file_url
        checksums = []
        files = []
        params = []
        for filename in filenames:
            if isinstance(filename, str):
                if (os.access(filename, os.F_OK)):
                    files.append(('file', open(filename, 'rb')))
                    checksums.append(self.get_file_checksum(filename))  
                else:
                    raise Exception("File not found: " + filename)
            else:
                files.append(('file', filename))

        data = {'item': json.dumps(item)}
        params = {} if scrape_file is True else {'scrapeFile':'false'}
        if 'id' in item and item['id']:
            data['id'] = item['id']
            url = '{0}?id={1}&'.format(self._base_upload_file_url, item['id'])
        else:
            url = '{0}?'.format(self._base_upload_file_url)

        for i, checksum in enumerate(checksums):
            url += 'md5Checksum={0}'.format(checksum) if i == 0 else '&md5Checksum={0}'.format(checksum)

        ret = self._session.post(url, params=params, files=files, data=data)
        # Close any open files
        for f in files:
            f[1].close()
        return self._get_json(ret)

    def upload_file(self, filename, mimetype=None):
        """ADVANCED USE -- USE OTHER UPLOAD METHODS IF AT ALL POSSIBLE. Upload a file to ScienceBase.  The file will
        be staged in a temporary area.  In order to attach it to an Item, the pathOnDisk must be added to an Item
        files entry, or one of a facet's file entries.

        :param filename: File to upload
        :param mimetype: MIME type of the file
        :return: JSON response from ScienceBase
        """
        self._refresh_check()
        retval = None
        url = self._base_upload_file_temp_url

        if os.access(filename, os.F_OK):
            # if no mimetype was sent in, try to guess
            if mimetype is None:
                mimetype = client._guess_mimetype(filename)
            fname = os.path.basename(filename)
            checksum = self.get_file_checksum(filename)
            with open(filename, 'rb') as f:
                ret = self._session.post(url, params={'md5Checksum': checksum}, files=[('files[]', (fname, f, mimetype))])
                return ret
                retval = self._get_json(ret)
        else:
            raise Exception("File not found: " + filename)
        return retval

    def replace_file(self, filename, item):
        """Replace a file on a ScienceBase Item.  This method will replace all files named
        the same as the new file, whether they are in the files list or on a facet.

        :param filename: Name of the file to replace
        :param item: ScienceBase Catalog Item JSON of the Item on which to replace the file
        :return: ScienceBase Catalog Item JSON of the updated Item
        """
        self._refresh_check()
        fname = os.path.basename(filename)
        #
        # replace file in files list
        #
        statinfo = os.stat(filename)
        if statinfo.st_size > 5000000:
            print("File is too large.  Large files must be replaced with the UI.")
        if 'files' in item:
            new_files = []
            for f in item['files']:
                if f['name'] == fname:
                    f = self._replace_file(filename, f)
                new_files.append(f)
            item['files'] = new_files
        #
        # replace file in facets
        #
        if 'facets' in item:
            new_facets = []
            for facet in item['facets']:
                if 'files' in facet:
                    new_files = []
                    for f in facet['files']:
                        if f['name'] == fname:
                            f = self._replace_file(filename, f)
                        new_files.append(f)
                    facet['files'] = new_files
                new_facets.append(facet)
            item['facets'] = new_facets
        self.update_item(item)
        return item

    def _replace_file(self, filename, itemfile):
        """Upload a file to ScienceBase and update file json with new path on disk.

        :param filename: Name of the file to replace
        :param itemfile: ScienceBase Catalog ItemFile JSON
        :return: ScienceBase Catalog ItemFile JSON after the replace
        """
        #
        # Upload file and point file JSON at it
        #
        self._refresh_check()
        upld_json = self.upload_file(filename, itemfile['contentType']).json()
        itemfile['pathOnDisk'] = upld_json[0]['fileKey']
        itemfile['dateUploaded'] = upld_json[0]['dateUploaded']
        itemfile['uploadedBy'] = upld_json[0]['uploadedBy']
        itemfile['checksum']= {'value': self.get_file_checksum(filename), 'type': 'MD5'}

        return itemfile

    def get_file_checksum(self, filename):
        """Get checksum value for a file (md5 Checksum from hashlib package)
        
        :param filename: File to get checksum on
        """
        with open(filename, 'rb') as f:
            file_hash = hashlib.md5()
            chunk = f.read(8192)
            while chunk:
                file_hash.update(chunk)
                chunk = f.read(8192)
            return file_hash.hexdigest()

    def delete_file(self, sb_filename, item):
        """Delete a file on a ScienceBase Item.  This method will delete all files with the provided
        name, whether they are in the files list or on a facet.

        :param sb_filename: Name of the file to delete
        :param item: ScienceBase Catalog Item JSON of the Item on which to delete the file
        :return: ScienceBase Catalog Item JSON of the updated Item
        """
        self._refresh_check()
        fname = sb_filename
        #
        # remove file in files list
        #

        if 'files' in item:
            new_files = []
            for f in item['files']:
                if f['name'] == fname:
                    pass #Drop the deleted file from the SBJSON
                else:
                    new_files.append(f)
            item['files'] = new_files
        #
        # remove file in facets
        #
        if 'facets' in item:
            new_facets = []
            for facet in item['facets']:
                if 'files' in facet:
                    new_files = []
                    for f in facet['files']:
                        if f['name'] == fname:
                            pass  # Drop the deleted file from the SBJSON
                        else:
                            new_files.append(f)
                    facet['files'] = new_files
                new_facets.append(facet)
            item['facets'] = new_facets
        self.update_item(item)

    def get_item_files_zip(self, item, destination='.'):
        """Download all files from a ScienceBase Item as a zip.  The zip is created server-side
        and streamed to the client.

        :param item: ScienceBase Catalog Item JSON of the item from which to download files
        :param destination:  Destination directory in which to store the zip file
        :return: The full name and path of the downloaded file
        """
        self._refresh_check()
        #
        # First check that there are files attached to the item, otherwise the call
        # to ScienceBase will return an empty zip file
        #
        file_info = self.get_item_file_info(item)
        if not file_info:
            return None

        #
        # Download the zip
        #
        r = self._session.get(self._base_download_files_url + item['id'], stream=True)
        local_filename = os.path.join(destination, item['id'] + ".zip")

        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)
                    f.flush()
        return local_filename

    def get_item_file_info(self, item):
        """Retrieve file information from a ScienceBase Item

        :param item: ScienceBase Catalog Item JSON of the item from which to get file information
        :return: A list of dictionaries containing url, name and size of each file

        """
        self._refresh_check()
        retval = []
        if item:
            #
            # regular files
            #
            if 'files' in item:
                for f in item['files']:
                    finfo = {}
                    if 'url' in f:
                        finfo['url'] = f['url']
                    if 'name' in f:
                        finfo['name'] = f['name']
                    if 'size' in f:
                        finfo['size'] = f['size']
                    if 'originalMetadata' in f:
                        finfo['originalMetadata'] = f['originalMetadata']
                    if 'contentType' in f:
                        finfo['contentType'] = f['contentType']
                    retval.append(finfo)
            if 'facets' in item:
                for facet in item['facets']:
                    if 'files' in facet:
                        for f in facet['files']:
                            finfo = {}
                            if 'url' in f:
                                finfo['url'] = f['url']
                            if 'name' in f:
                                finfo['name'] = f['name']
                            if 'size' in f:
                                finfo['size'] = f['size']
                            if 'originalMetadata' in f:
                                finfo['originalMetadata'] = f['originalMetadata']
                            if 'contentType' in f:
                                finfo['contentType'] = f['contentType']
                            retval.append(finfo)
        return retval

    def download_file(self, url, local_filename, destination='.', progress_bar=False, use_requests=False):
        """Download file from URL

        :param url: ScienceBase Catalog Item file download URL
        :param local_filename: Name to use for the local file
        :param destination: Destination directory in which to store the files
        :param progress_bar: Boolean to turn on progress bar printing
        :return: The full name and path of the downloaded file
        """
        self._refresh_check()
        complete_name = os.path.join(destination, local_filename)
        print("downloading " + url + " to " + complete_name)
        response = None
        # if downloading a presigned URL cloud resource, use requests.get
        # to avoid multiple authorizations error:
        if use_requests == True: 
            response = requests.get(url, stream=True)
        else:
            response = self._session.get(url, stream=True)

        # https://stackoverflow.com/a/15645088/3362993
        download_length = 0
        if progress_bar is True:
            try:
                total_length = int(response.headers.get('content-length'))
            except Exception:
                try:
                    total_length = int(requests.head(url, headers={'Accept-Encoding': None}).headers.get("content-length"))
                except Exception:
                    print("No 'content-length' header found to populate progress bar.")
                    progress_bar=False

        with open(complete_name, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk: # filter out keep-alive new chunks
                    download_length += len(chunk)
                    f.write(chunk)
                    f.flush()
                    if progress_bar is True:
                        done = int(50 * download_length / total_length)
                        sys.stdout.write("\r[%s%s]" % ('=' * done, ' ' * (50-done)) + " " + str(int(download_length / total_length * 100)) + "%")
                        sys.stdout.flush()
            if progress_bar is True:
                sys.stdout.write('\n')
        return complete_name

    def get_item_files(self, item, destination='.', progress_bar=False):
        """Download the individual files attached to a ScienceBase Item

        :param item: ScienceBase Catalog Item JSON of the item from which to download files
        :param destination: Destination directory in which to store the files
        :param progress_bar: Boolean to turn on progress bar printing
        :return: The ScienceBase Catalog file info JSON response
        """
        self._refresh_check()
        file_info = self.get_item_file_info(item)
        for finfo in file_info:            
            self.download_file(finfo['url'], finfo['name'], destination, progress_bar)
        return file_info

    def get_my_items_id(self):
        """Get the ID of the logged-in user's My Items

        :return: The ScienceBase Catalog Item ID of the logged in user's My Items folder
        """
        self._refresh_check()
        ret = None
        if self._username:
            params = {'q': '', 'lq': 'title.untouched:"' + self._username + '"'}
            if self._users_id:
                params['parentId'] = self._users_id
            items = self.find_items(params)
            if 'items' in items:
                for item in items['items']:
                    if item['title'] == self._username:
                        ret = item['id']
                        break
        return ret

    def get_child_ids(self, parentid):
        """Get IDs of all immediate children for a given parent

        :param parentid: ScienceBase Catalog Item ID of the item for which to look for children
        :return: A List of ScienceBase Catalog Item IDs of the direct children
        """
        self._refresh_check()
        retval = []
        items = self.find_items({'filter':'parentIdExcludingLinks=' + parentid, 'max': self._max_item_count})
        while items and 'items' in items:
            for item in items['items']:
                retval.append(item['id'])
            items = self.next(items)
        return retval

    def get_ancestor_ids(self, parentid):
        """Get IDs of all descendants of given item excluding those which are linked in (short-cutted).
        Finds items by ancestorsExcludingLinks.

        :param parentid: ScienceBase Catalog Item ID of the item for which to look for descendants
        :return: A List of ScienceBase Catalog Item IDs of the descendants
        """
        self._refresh_check()
        retval = []
        items = self.find_items({'filter':'ancestorsExcludingLinks=' + parentid, 'max': self._max_item_count})
        while items and 'items' in items:
            for item in items['items']:
                retval.append(item['id'])
            items = self.next(items)
        return retval

    def get_shortcut_ids(self, itemid):
        """Get IDs of all shortcutted items for a given item

        :param itemid: ScienceBase Catalog Item ID of the item for which to return shortcuts
        :return: A list of ScienceBase Catalog Item IDs to which the Item is shortcutted
        """
        self._refresh_check()
        retval = []
        items = self.find_items({'filter':'linkParentId=' + itemid})
        while items and 'items' in items:
            for item in items['items']:
                retval.append(item['id'])
            items = self.next(items)
        return retval

    def create_shortcut(self, itemid, parentid):
        """Create a shortcut to another item

        :param itemid: ScienceBase Catalog Item ID of shortcutted item
        :param parentid: ScienceBase Catalog Item ID of item containing the shortcut
        :return: JSON response from ScienceBase Catalog
        """
        self._refresh_check()
        ret = self._session.post(self._base_shortcut_item_url, params={'itemId':itemid, 'destId':parentid})
        return self._get_json(ret)

    def remove_shortcut(self, itemid, parentid):
        """Remove a shortcut to another item

        :param itemid: ScienceBase Catalog Item ID of shortcutted item
        :param parentid: ScienceBase Catalog Item ID of item containing the shortcut
        :return: JSON response from ScienceBase Catalog
        """
        self._refresh_check()
        ret = self._session.post(self._base_unlink_item_url, params={'itemId':itemid, 'destId':parentid})
        return self._get_json(ret)

    def get_NetCDFOPeNDAP_info_facet(self, url):
        """Given an OPeNDAP URL, create a NetCDFOPeNDAP facet from the return data

        :param url: OPeNDAP URL to query
        :return: ScienceBase Catalog Item facet JSON with information on the OPeNDAP service
        """
        self._refresh_check()
        data = self._get_json(self._session.post(self._base_sb_url + 'items/scrapeNetCDFOPeNDAP', params={'url': url}))
        facet = {}
        facet['className'] = 'gov.sciencebase.catalog.item.facet.NetCDFOPeNDAPFacet'
        facet['title'] = data['title']
        facet['summary'] = data['summary']
        facet['boundingBox'] = {}
        facet['boundingBox']['minX'] = data['boundingBox']['minX']
        facet['boundingBox']['maxX'] = data['boundingBox']['maxX']
        facet['boundingBox']['minY'] = data['boundingBox']['minY']
        facet['boundingBox']['maxY'] = data['boundingBox']['maxY']
        facet['variables'] = data['variables']
        return facet

    def add_extent(self, item_id, feature_geojson):
        """Create an extent from Feature or FeatureCollection geojson and add it to the item's footprint.
        There are several properties that ScienceBase stores in the master extents
        table: name, shortName, description, and promotedForReuse.  If desired,
        they are stored in the feature_geojson['properties'] dict.

        :param item_id: ScienceBase Catalog Item ID of the item to which to add the extent
        :param feature_geojson: GeoJSON describing the extent to create
        :return: ScienceBase Catalog Item JSON of the updated item.
        """
        self._refresh_check()
        features = feature_geojson['features'] if feature_geojson['type'] == "FeatureCollection" else [feature_geojson]
        # Get the item from ScienceBase
        item = self.get_item(item_id)
        # Save the existing item extents
        extents = item['extents'] if 'extents' in item else []
        for feature in features:
            # Create the new extent, which will overwrite the exiting extent ID list
            item['extents'] = [feature]
            item = self.update_item(item)
            extents.extend(item['extents'])
        # If there were extents on the item, add them back
        if len(extents) > 1:
            item['extents'] = extents
            item = self.update_item(item)
        # Return the item JSON
        return item

    def find_items(self, params):
        """Search for ScienceBase items

        :param params: ScienceBase Catalog search parameters
        :return: ScienceBase Catalog search response object containing the next page of results for the search
        """
        return self.get_json(self._base_items_url, params=params)

    def next(self, items):
        """Get the next set of items from the search

        :param items: ScienceBase Catalog search response object from a prior search
        :return: ScienceBase Catalog search response object containing the next page of results for the search
        """
        ret_val = None
        # Items response
        if 'nextlink' in items:
            ret_val = self.get_json(items['nextlink']['url'])
        # Hidden properties response
        elif 'links' in items and 'next' in items['links']:
            ret_val = self.get_json(items['links']['next'])
        return ret_val

    def previous(self, items):
        """Get the previous set of items from the search

        :param items: ScienceBase Catalog search response object from a prior search
        :return: ScienceBase Catalog search response object containing the previous page of results for the search
        """
        ret_val = None
        # Items response
        if 'prevlink' in items:
            ret_val = self.get_json(items['prevlink']['url'])
        # Hidden properties response
        elif 'links' in items and 'prev' in items['links']:
            ret_val = self.get_json(items['links']['prev'])
        return ret_val

    def find_items_by_any_text(self, text):
        """Search for ScienceBase items by free text

        :param text: Text to search for in all searchable fields of ScienceBase Catalog Items
        :return: ScienceBase Catalog search response containing results
        """
        return self.find_items({'q': text})

    def find_items_by_title(self, text):
        """Search for ScienceBase items by title

        :param text: Text to search for in the title field
        :return: ScienceBase Catalog search response containing results
        """
        return self.find_items({'q': '', 'lq': 'title:"' + text + '"'})

    def get(self, url, encoding = None):
        """Get the text response of the given URL

        :param url: URL to request via HTTP GET
        :param encoding: Encoding string ("utf-8", "ISO-8859-1", etc.)
        :return: TEXT response
        """
        response = self._session.get(url)
        if encoding is not None:
            response.encoding = encoding
        return self._get_text(response)

    def get_json(self, url, params = None):
        """Get the JSON response of the given URL

        :param url: URL to request via HTTP GET
        :return: JSON response
        """
        ret = None
        if params:
            ret = self._get_json(self._session.get(url, params=params))
        else:
            ret = self._get_json(self._session.get(url))
        return ret

    def get_directory_contact(self, party_id):
        """Get the Directory Contact JSON for the contact with the given party ID

        :param party_id: ScienceBase Directory Party ID of the contact to get
        :return: ScienceBase Directory contact JSON
        """
        ret = self._session.get(self._base_person_url + party_id)
        return self._get_json(ret)

    def get_sbcontact_from_directory_contact(self, directory_contact, sbcontact_type):
        """Convert the given Directory Contact JSON into valid ScienceBase Item contact JSON

        :param directory_contact: ScienceBase Directory Contact JSON to transform
        :param sbcontact_type: ScienceBase Item Contact type
        :return: ScienceBase Catalog contact JSON
        """
        sbcontact = {}

        sbcontact['name'] = directory_contact['displayName']
        sbcontact['oldPartyId'] = directory_contact['id']
        sbcontact['type'] = sbcontact_type
        if 'organization' in directory_contact:
            sbcontact['organization'] = {'displayText': directory_contact['organizationDisplayText']}
        if 'email' in directory_contact:
            sbcontact['email'] = directory_contact['email']
        if 'firstName' in directory_contact:
            sbcontact['firstName'] = directory_contact['firstName']
        if 'lastName' in directory_contact:
            sbcontact['lastName'] = directory_contact['lastName']
        if 'middleName' in directory_contact:
            sbcontact['middleName'] = directory_contact['middleName']
        if 'streetAddress' in directory_contact or 'mailAddress' in directory_contact:
            sbcontact['primaryLocation'] = {}
            if 'streetAddress' in directory_contact:
                sbcontact['primaryLocation']['streetAddress'] = directory_contact['primaryLocation']['streetAddress']
            if 'mailAddress' in directory_contact:
                sbcontact['primaryLocation']['mailAddress'] = directory_contact['primaryLocation']['mailAddress']

        return sbcontact

    def _get_json(self, response):
        """Check the status code of the response, and return the JSON

        :param response: HTTP response to check and parse JSON from
        :return: The JSON from the HTTP response
        """
        self._check_errors(response)
        try:
            return response.json()
        except Exception as exc:
            raise Exception("Error parsing JSON response: " + response.text) from exc

    def _get_text(self, response):
        """Check the status code of the response, and return the text

        :param response:
        :return:
        """
        self._check_errors(response)
        try:
            return response.text
        except Exception as exc:
            raise Exception("Error parsing response") from exc

    def _check_errors(self, response):
        """Check the status code of the response

        :param response: HTTP response to check
        :return: HTTP response, provided an error did not occur in the request
        """
        if response.status_code == 404:
            if "The specified URL cannot be found" in response.text:
                raise Exception("Request blocked by the USGS web application firewall")
            else:
                raise Exception("Resource not found, or user does not have access")
        elif response.status_code == 401:
            raise Exception("Unauthorized access")
        elif response.status_code == 429:
            raise Exception("Too many requests")
        elif response.status_code != 200 and response.status_code != 201:
            if self._retry:
                return response
            else:
                raise Exception("Other HTTP error: " + str(response.status_code) + ": " + response.text)
        if "MyUSGS : Login" in response.text:
            raise Exception("Not logged in")
            
    def _remove_josso_param(self, url):
        """Remove JOSSO parameter from URL

        :param url: URL to clean
        :return: URL with JOSSO parameter removed
        """
        o = urlparse.urlsplit(url)
        q = [x for x in urlparse.parse_qsl(o.query) if "josso" not in x]
        return urlparse.urlunsplit((o.scheme, o.netloc, o.path, urlencode(q), o.fragment))

    def debug(self):
        """Turn on HTTP logging for debugging purposes.
        This enables debugging at httplib level (requests->urllib3->httplib)
        You will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
        The only thing missing will be the response.body which is not logged.
        """
        httplib.HTTPConnection.debuglevel = 1

        logging.basicConfig()
        logging.getLogger().setLevel(logging.DEBUG)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True

    ACL_ADD = "ADD"
    """ Add ACL """

    ACL_REMOVE = "REMOVE"
    """ Remove ACL """

    ACL_READ = "read"
    """ Read ACL """

    ACL_WRITE = "write"
    """ Write ACL """

    def get_permissions(self, item_id):
        """Get permission JSON for the item identified by item_id

        :param item_id: The ID of the ScienceBase item
        :return: The permissions JSON for the given item
        """
        return self.get_json(self._base_item_url + item_id + "/permissions/")

    def set_permissions(self, item_id, acls):
        """Set permissions for the item identified by item_id. WARNING: Advanced use only. ACL JSON 
        must be created properly. Use one of the ACL helper methods if at all possible.

        :param item_id: The ID of the ScienceBase item
        :param acls: ACL JSON
        :return: The permissions JSON for the given item
        """
        return self._get_json(self._session.put(self._base_item_url + item_id + "/permissions/", data=json.dumps(acls)))

    def add_acl_user_read(self, user_name, item_id):
        """Add a READ ACL for the given user on the specified item.

        :param user_name: User for which to add READ permissions
        :param item_id: The ID of the ScienceBase item        
        :return: The permissions JSON for the given item
        """
        return self._update_acls(self.ACL_ADD, self.ACL_READ, "USER:%s" % user_name, item_id)

    def remove_acl_user_read(self, user_name, item_id):
        """Remove the READ ACL for the given user on the specified item.

        :param user_name: User for which to remove READ permissions
        :param item_id: The ID of the ScienceBase item        
        :return: The permissions JSON for the given item
        """
        return self._update_acls(self.ACL_REMOVE, self.ACL_READ, "USER:%s" % user_name, item_id)

    def add_acl_user_write(self, user_name, item_id):
        """Add a WRITE ACL for the given user on the specified item.

        :param user_name: User for which to add WRITE permissions
        :param item_id: The ID of the ScienceBase item        
        :return: The permissions JSON for the given item
        """
        return self._update_acls(self.ACL_ADD, self.ACL_WRITE, "USER:%s" % user_name, item_id)

    def remove_acl_user_write(self, user_name, item_id):
        """Remove a WRITE ACL for the given user on the specified item.

        :param user_name: User for which to remove WRITE permissions
        :param item_id: The ID of the ScienceBase item        
        :return: The permissions JSON for the given item
        """
        return self._update_acls(self.ACL_REMOVE, self.ACL_WRITE, "USER:%s" % user_name, item_id)

    def add_acl_role_read(self, role_name, item_id):
        """Add a READ ACL for the given role on the specified item.

        :param role_name: Role for which to add READ permissions
        :param item_id: The ID of the ScienceBase item        
        :return: The permissions JSON for the given item
        """
        return self._update_acls(self.ACL_ADD, self.ACL_READ, "ROLE:%s" % role_name, item_id)

    def remove_acl_role_read(self, role_name, item_id):
        """Remove a READ ACL for the given role on the specified item.

        :param user_name: Role for which to remove READ permissions
        :param item_id: The ID of the ScienceBase item        
        :return: The permissions JSON for the given item
        """
        return self._update_acls(self.ACL_REMOVE, self.ACL_READ, "ROLE:%s" % role_name, item_id)

    def add_acl_role_write(self, role_name, item_id):
        """Add a WRITE ACL for the given role on the specified item.

        :param user_name: Role for which to add WRITE permissions
        :param item_id: The ID of the ScienceBase item        
        :return: The permissions JSON for the given item
        """
        return self._update_acls(self.ACL_ADD, self.ACL_WRITE, "ROLE:%s" % role_name, item_id)

    def remove_acl_role_write(self, role_name, item_id):
        """Remove a WRITE ACL for the given role on the specified item.

        :param user_name: Role for which to remove WRITE permissions
        :param item_id: The ID of the ScienceBase item        
        :return: The permissions JSON for the given item
        """
        return self._update_acls(self.ACL_REMOVE, self.ACL_WRITE, "ROLE:%s" % role_name, item_id)

    def publish_to_public_bucket(self, item_id):
        """ call publish end point from catalog
            this should publish all files to public s3 publish bucket
            TODO: Fix documentation
        """
        return self._session.post(self._base_item_url + item_id + "/publishFilesToS3")

    def publish_array_to_public_bucket(self, item_id, filenames):
        """ publish a list of files on an item to the public s3 publish bucket

        :param item_id: The ID of the ScienceBase item
        :param filenames: a list of filenames to be published
        """
        for filename in filenames:
            item = self.get_item(item_id)
            pathOnDisk = ""
            cuid = ""

            if 'files' in item:
                for f in item['files']:
                    if 'name' in f:
                        if f['name'] == filename:
                            if 'pathOnDisk' in f:
                                pathOnDisk = f['pathOnDisk']
                            if 'cuid' in f:
                                cuid = f['cuid']
                            break
            if pathOnDisk == "":
                if 'facets' in item:
                    for facet in item['facets']:
                        if 'files' in facet:
                            for f in facet['files']:
                                if f['name'] == filename:
                                    if 'pathOnDisk' in f:
                                        pathOnDisk = f['pathOnDisk']
                                    if 'cuid' in f:
                                        cuid = f['cuid']
                                    break

            input = {"itemId": item_id, "filename": filename, "action": "publish", "pathOnDisk": pathOnDisk}

            response = self._sbSessionEx.publish_to_public_bucket(input)

            print(response)

            if response:
                print("Successfully published filename " + filename + " to public S3 bucket")
            else:
                print("Failed to publish file " + filename + " to public S3 bucket")

    def unpublish_array_from_public_bucket(self, item_id, filenames):
        """unpublish a list of files on an item from the public s3 publish bucket

        :param item_id: The ID of the ScienceBase item
        :param filenames: a list of filenames to be unpublished
        """
        if not self._sbSessionEx.is_logged_in():
            print(f'{self._username} not logged into Keycloak -- cloud services not available')
        else:
            item = self.get_item(item_id)

            for filename in filenames:
                cuid = ""
                key = ""

                if 'files' in item:
                    for f in item['files']:
                        if 'name' in f:
                            if f['name'] == filename:
                                if 'cuid' in f:
                                    cuid = f['cuid']
                                if 'key' in f:
                                    key = f['key']
                                break

                if cuid == "":
                    if 'facets' in item:
                        for facet in item['facets']:
                            if 'files' in facet:
                                for f in facet['files']:
                                    if f['name'] == filename:
                                        if 'cuid' in f:
                                            cuid = f['cuid']
                                        if 'key' in f:
                                            key = f['key']
                                        break

                if cuid is None:
                    cuid = ""

                input = {"cuid": cuid, "key": key}

                response = self._sbSessionEx.unpublish_from_public_bucket(input)

                if response:
                    print("Successfully unpublished filename " + filename + " from public S3 bucket")
                else:
                    print("Failed to unpublish file " + filename + " from public S3 bucket")

    def delete_cloud_files(self, item_id, filenames):
        """deletes a list of Cloud files on an item from the ScienceBase S3 content bucket and/or S3 publish bucket
        and updates the item JSON accordingly

        *can handle deletion of files from the S3 buckets to clean up the backend even if the item JSON is out of sync
        (i.e. the files are not referenced in the item JSON)

        :param item_id: The ID of the ScienceBase item
        :param filenames: a list of filenames to be deleted
        """
        if not self._sbSessionEx.is_logged_in():
            print(f'{self._username} not logged into Keycloak -- cloud services not available')
        else:
            item = self.get_item(item_id)

            for filename in filenames:

                cuid = ""
                key = ""

                if 'files' in item:
                    for f in item['files']:
                        if 'name' in f:
                            if f['name'] == filename:
                                if 'cuid' in f:
                                    cuid = f['cuid']
                                if 'key' in f:
                                    key = f['key']
                                break

                if cuid == "":
                    if 'facets' in item:
                        for facet in item['facets']:
                            if 'files' in facet:
                                for f in facet['files']:
                                    if f['name'] == filename:
                                        if 'cuid' in f:
                                            cuid = f['cuid']
                                        if 'key' in f:
                                            key = f['key']
                                        break

                # handle deletion of files from S3 buckets when the item JSON is out of sync
                if cuid == "" and key == "":
                    print("File " + filename + " not found on item")
                    print("Will proceed to check for this file in the S3 content bucket and publish bucket and delete it from those locations if found.")

                    key_val = item_id + "/" + filename

                    params = {
                        "key": key_val,
                        "sb_env": self._env
                    }

                    if self._env == 'beta' or self._env == 'dev':
                        delete_s3_file_url = "https://tqvcfyruhb.execute-api.us-west-2.amazonaws.com/prod/deleteS3Files"
                    else:
                        delete_s3_file_url = "https://ksrs49weqg.execute-api.us-west-2.amazonaws.com/prod/deleteS3Files"

                    resp = self._session.post(delete_s3_file_url, json=params)

                    print("Check completed.")

                else:
                    if cuid is None:
                        cuid = ""

                    if filename.endswith(".sd"):
                        self.stop_esri_service(item_id, filename)

                        #delete the .sd facet
                        client_mutation_id = "delete_sd_facet"

                        f = {}

                        if 'facets' in item:
                            facets = item['facets']
                        else:
                            facets = []

                        for facet in facets:
                            if facet['name'] == filename:
                                f = facet
                                break

                        if f in facets:
                            facets.remove(f)

                        input = {
                            "clientMutationId": client_mutation_id,
                            "id": item_id,
                            "itemPatch": {
                                "facets": facets
                            }
                        }

                        requests_session = requests.session()

                        graphql_url = self._sbSessionEx.get_graphql_url()

                        query = """ mutation UpdateItem($input: UpdateItemInput!) {
                                            updateItem(input: $input) {
                                                item {
                                                    distributionLinks {
                                                        uri
                                                    }
                                                }
                                            }
                                          }
                                        """

                        failed_retry_time = 10
                        for tries in range(3):
                            try:
                                resp = requests_session.post(
                                    graphql_url,
                                    headers=self._sbSessionEx.get_header(),
                                    json={'query': query, 'variables': {'input': input}}
                                )
                                break
                            except requests.exceptions.Timeout as e:
                                print("DeleteSdFacet Timeout: " + repr(e))
                            except requests.exceptions.RequestException as e:
                                print("DeleteSdFacet RequestException: " + repr(e))
                            # Wait before we try again
                            time.sleep(failed_retry_time)
                            failed_retry_time *= 2

                        print("RESPONSE (GRAPHQL): " + resp.text)

                        if "SyntaxError" in resp.text:
                            print("SyntaxError: " + resp.text)
                        else:
                            print("DeleteSdFacet Completed Successfully")

                    input = {"cuid": cuid, "key": key}

                    response = self._sbSessionEx.delete_cloud_file(input)
                    print(response)

                    # handle deletion of on-premise files published to public bucket
                    if cuid == "":
                        key_val = item_id + "/" + filename

                        params = {
                            "key": key_val,
                            "sb_env": self._env
                        }

                        if self._env == 'beta' or self._env == 'dev':
                            delete_s3_file_url = "https://tqvcfyruhb.execute-api.us-west-2.amazonaws.com/prod/deleteS3Files"
                        else:
                            delete_s3_file_url = "https://ksrs49weqg.execute-api.us-west-2.amazonaws.com/prod/deleteS3Files"

                        resp = self._session.post(delete_s3_file_url, json=params)

                    if 'errors' in response:
                        print("Failed to delete file " + filename)
                        print("Please try again.")
                        if 'INTERNAL_SERVER_ERROR' in response:
                            print("Internal server error. Please check to make sure this file is a cloud file.")
                    else:
                        print("Successfully deleted " + filename + " from ScienceBase item and associated S3 bucket(s)")

    def start_esri_service(self, item_id, filename):
        """Creates a spatial service on a ScienceBase service definition (.sd) file in ArcGIS Online or ArcGIS Server.
        The service definition file must have been published to the public ScienceBase S3 bucket.
        User will receive an email notification when process is complete.
               :param item_id: The ID of the ScienceBase item
               :param filename: The filename of the .sd file (only works for files in the public S3 bucket)
        """
        if not self.is_logged_in():
            print("Please log in and retry.")
            return False
        else:
            is_published = False

            item = self.get_item(item_id)

            if 'files' in item:
                for f in item['files']:
                    if 'name' in f:
                        if f['name'] == filename:
                            if 'publishedS3Uri' in f:
                                is_published = True
                                break
            if not is_published:
                if 'facets' in item:
                    for facet in item['facets']:
                        if 'files' in facet:
                            for f in facet['files']:
                                if f['name'] == filename:
                                    if 'publishedS3Uri' in f:
                                        is_published = True

            if not is_published:
                print("Error: the .sd file has not been published to the public S3 bucket. Please publish it and retry.")
                return False

            else:
                input = {"itemId": item_id, 
                        "fileName": filename, 
                        "taskType": "publish"}

                requests_session = requests.session()

                graphql_url = self._sbSessionEx.get_graphql_url()

                query = """ mutation triggerAgolTask($input: triggerAgolTaskInput!) {
                                triggerAgolTask(input: $input) {
                                    itemId
                                    fileName
                                    taskInitialized
                                    statusCode
                                }
                            }
                        """

                failed_retry_time = 10
                for tries in range(3):
                    try:
                        resp = requests_session.post(
                            graphql_url,
                            headers=self._sbSessionEx.get_header(),
                            json={'query': query, 'variables': {'input': input}}
                        )
                        break
                    except requests.exceptions.Timeout as e:
                        print("TriggerAgolTask Timeout: " + repr(e))
                    except requests.exceptions.RequestException as e:
                        print("TriggerAgolTask RequestException: " + repr(e))
                    # Wait before we try again
                    time.sleep(failed_retry_time)
                    failed_retry_time *= 2

                print("RESPONSE (GRAPHQL): " + resp.text)

                if "SyntaxError" in resp.text:
                    print("SyntaxError: " + resp.text)
                    return False
                else:
                    print("Triggered spatial service creation in ArcGIS Online.")
                    return True

    def stop_esri_service(self, item_id, filename):
        """Stops a spatial service that had been published on a ScienceBase service definition (.sd) file in ArcGIS Online or ArcGIS Server.
               :param item_id: The ID of the ScienceBase item
               :param filename: The filename of the .sd file in ScienceBase on which the ArcGIS Online or ArcGIS Server spatial service had been published
        """
        if not self.is_logged_in():
            print("Please log in and retry.")
            return False
        else:
            try:
                item = self.get_item(item_id)

                if 'facets' in item:
                    for facet in item['facets']:
                        if facet['name'] == filename:
                            if 'serverType' in facet:
                                if facet['serverType'] == 'AGOL_Feature_Server' or facet['serverType'] == 'AGOL_WMTS_Server':
                                    input = {"itemId": item_id, 
                                            "fileName": filename, 
                                            "taskType": "delete"}

                                    requests_session = requests.session()

                                    graphql_url = self._sbSessionEx.get_graphql_url()

                                    query = """ mutation triggerAgolTask($input: triggerAgolTaskInput!) {
                                                    triggerAgolTask(input: $input) {
                                                        itemId
                                                        fileName
                                                        taskInitialized
                                                        statusCode
                                                    }
                                                }
                                            """

                                    failed_retry_time = 10
                                    for tries in range(3):
                                        try:
                                            resp = requests_session.post(
                                                graphql_url,
                                                headers=self._sbSessionEx.get_header(),
                                                json={'query': query, 'variables': {'input': input}}
                                            )
                                            break
                                        except requests.exceptions.Timeout as e:
                                            print("TriggerAgolTask Timeout: " + repr(e))
                                        except requests.exceptions.RequestException as e:
                                            print("TriggerAgolTask RequestException: " + repr(e))
                                        # Wait before we try again
                                        time.sleep(failed_retry_time)
                                        failed_retry_time *= 2

                                    print("RESPONSE (GRAPHQL): " + resp.text)

                                    if "SyntaxError" in resp.text:
                                        print("SyntaxError: " + resp.text)
                                        return False
                                    else:
                                        print("Triggered spatial service deletion in ArcGIS Online.")
                                        return True
                                        
                            elif 'servicePath' in facet and 'serviceId' in facet and 'processingState' in facet:
                                if facet['servicePath'] != '' and facet['serviceId'] != '' and facet['processingState'] == 'success':
                                    payload = {'operation': 'delete'}
                                    if self._env == 'beta' or self._env == 'dev':
                                        url = "https://beta.sciencebase.gov/catalog/item/createProcessJob/" + item_id
                                    else:
                                        url = "https://www.sciencebase.gov/catalog/item/createProcessJob/" + item_id
                                    self._session.get(url, params=payload)
                                    print("Triggered deletion of spatial service from ScienceBase ArcGIS Server instance.")
                                    return True

                print("Error: published ArcGIS service not found. Please publish the service before attempting to delete it.")
                return False

            except Exception as e:
                print("Error: " + repr(e))
                return False

    def publish_item(self, item_id):
        """Publish the item, adding PUBLIC read permissions. User must be USGS or in the publisher role.
        :param item_id: The ID of the ScienceBase item
        :return: The permissions JSON for the given item
        """
        return self._update_acls(self.ACL_ADD, self.ACL_READ, "PUBLIC", item_id)
    
    def unpublish_item(self, item_id):
        """Unpublish the item, removing PUBLIC read permissions.
        :param item_id: The ID of the ScienceBase item
        :return: The permissions JSON for the given item
        """
        return self._update_acls(self.ACL_REMOVE, self.ACL_READ, "PUBLIC", item_id)

    def _update_acls(self, add_remove, read_write, acl_name, item_id):
        """Update ACLs for the specified item.

        :param add_remove: ACL_ADD or ACL_REMOVE to specify operation
        :param read_write: ACL_READ or ACL_WRITE to specify permission type
        :param acl_name: Role or user update
        :param item_id: The ID of the ScienceBase item
        :return: The permissions JSON for the given item
        """
        acls = self.get_permissions(item_id)
        if read_write in acls:
            if ('acl' not in acls[read_write]):
                acls[read_write]['acl']=[]
            if add_remove == self.ACL_ADD and acl_name not in acls[read_write]['acl']: 
                acls[read_write]['acl'].append(acl_name)
            elif add_remove == self.ACL_REMOVE and acl_name in acls[read_write]['acl']:
                acls[read_write]['acl'].remove(acl_name)
            acls[read_write]['inherited'] = False
            acls.pop('inheritsFromId', None)
            acls = self.set_permissions(item_id, acls)
        return acls

    def set_acls_inherit(self, read_write, item_id):
        """Set the item to inherit ACLs from its parent item.

        :param read_write: ACL_READ or ACL_WRITE to specify permission type
        :param item_id: The ID of the ScienceBase item
        :return: The permissions JSON for the given item
        """
        acls = self.get_permissions(item_id)
        acls[read_write]['inherited'] = True
        return self.set_permissions(item_id, acls)

    def set_acls_inherit_read(self, item_id):
        """Set the item to inherit READ ACLs from its parent item.

        :param item_id: The ID of the ScienceBase item
        :return: The permissions JSON for the given item
        """
        return self.set_acls_inherit(self.ACL_READ, item_id)

    def set_acls_inherit_write(self, item_id):
        """Set the item to inherit WRITE ACLs from its parent item.

        :param item_id: The ID of the ScienceBase item
        :return: The permissions JSON for the given item
        """
        return self.set_acls_inherit(self.ACL_WRITE, item_id)
        
    def has_public_read(self, acls):
        """Return whether the given ACLs include public READ permissions.

        :param acls: Item ACL JSON
        :return: Whether the given ACLs include public READ permissions.
        """
        return 'PUBLIC' in acls['read']['acl'] if 'read' in acls and 'acl' in acls['read'] else False
        
    def print_acls(self, acls):
        """Pretty print the given ACL JSON.

        :param acls: Item ACL JSON
        """
        print("Read ACLs:")
        if 'inherited' in acls['read']:
            print("\tinherited:" + str(acls['read']['inherited']))
        if 'acl' in acls['read']:
            for read_acl in acls['read']['acl']:
                print("\t" + read_acl)
        
        print("Write ACLs:")
        if 'inherited' in acls['write']:
            print("\tinherited:" + str(acls['write']['inherited']))
        if 'acl' in acls['write']:
            for write_acl in acls['write']['acl']:
                print("\t" + write_acl)

    def get_item_link_types(self):
        """Get ItemLink type JSON list from the vocabulary server.

        :return: JSON of all available ItemLink types
        """ 
        url = "%s%s" % (self._base_sb_url.replace('catalog','vocab'), "4f4e475de4b07f02db47decc/terms")
        response = self.get_json(url)
        return response['list'] if response and 'list' in response else []

    def get_item_link_type_by_name(self, link_type_name):
        """Get ItemLink type JSON object from the vocabulary server for the given type.

        :param link_type_name: Name of the ItemLink type
        :return: ItemLink type JSON object from the vocabulary server for the given type
        """ 
        ret = None
        types = self.get_item_link_types()
        for link_type in types:
            print(link_type['name'])
            if link_type['name'] == link_type_name:
                ret = link_type
                break
        return ret

    def get_item_links(self, item_id):
        """Get ItemLink (relationship) JSON describing relationships involving the Item with the given ID.

        :param item_id: Item ID
        :return: ItemLink JSON
        """
        return self.get_json('%s%s' % (self._base_item_link_url, item_id))

    def create_item_link(self, from_item_id, to_item_id, link_type_id, reverse=False):
        """Create an ItemLink (relationship) between the two items of the specified type.

        :param from_item_id: From item. This item must be writeable by the caller.
        :param to_item_id: To item
        :param link_type_id: ID of the link type (retrieve using get_item_link_types or get_item_link_type_by_name)
        :param reverse: Whether to reverse the relationsip
        :return: ItemLink JSON
        """
        item_link_json = {
            "itemLinkTypeId": link_type_id
        }
        item_link_json['itemId'] = from_item_id
        item_link_json['relatedItemId'] = to_item_id
        if reverse:
            item_link_json['reverseRelationship'] = True

        ret = self._session.post(f'{self._base_item_link_url}', data=json.dumps(item_link_json))
        return self._get_json(ret)

    def create_related_item_link(self, from_item_id, to_item_id):
        """Create a 'related' ItemLink (relationship) between the two items.

        :param from_item_id: From item
        :param to_item_id: To item
        :return: ItemLink JSON
        """
        related_item_link = self.get_item_link_type_by_name('related')
        return self.create_item_link(from_item_id, to_item_id, related_item_link['id'])