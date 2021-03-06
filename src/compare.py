##################################################################
# Source code for comparing MARC data with OCLC and LOC's MARC XML
# June 2020
##################################################################

# import functions
from bookops_worldcat import WorldcatAccessToken
from bookops_worldcat import MetadataSession
from configparser import ConfigParser
import xml.etree.ElementTree as ET
from datetime import datetime
import unidecode as udc
import mysql.connector
from tqdm import tqdm
import requests
import chardet
import string
import uuid
import time
import csv
import sys
import os
import re

# Get configuration
config = ConfigParser(os.environ)
config.read("compare_config.ini")
# Get passwords
passwords = ConfigParser(os.environ)
passwords.read("passwords.ini")

# Get local database user information
USER = passwords.get("local", "USER")
PASSWORD = passwords.get("local", "PASSWORD")
HOST = passwords.get("local", "HOST")
DATABASE = passwords.get("local", "DATABASE")

# Get OcLC user information
try:
    WC_KEY = passwords.get("oclc", "WC_KEY")
    SECRET = passwords.get("oclc", "SECRET")
    PRINCIPAL_ID = passwords.get("oclc", "PRINCIPAL_ID")
    PRINCIPAL_IDNS = passwords.get("oclc", "PRINCIPAL_IDNS")
except Exception as e:
    print("No OCLC keys provided")


USER_DEFINED_SUBFIELDS = config.get("subfields", "USER_DEFINED_SUBFIELDS")
USER_DEFINED_SUBFIELDS = [s.replace(" ", "") for s in USER_DEFINED_SUBFIELDS.split(',')]
USER_DEFINED_TAG = config.get("subfields", "USER_DEFINED_API_TAG")

# Throttle for LOC
T = 3

# General functions for analysis of MARC fields
#@profile
def compare_records(api, usr=USER, pwd=PASSWORD, limit=1000, hst=HOST, db=DATABASE, return_mode=True):
    '''
    Compare local library's MARC records with authority records from either the Library of Congress' (LOC) or
    OCLC.

    Inputs:
        - usr (str): local database user name
        - pwd (str): local database password
        - hst (str): local database host name
        - db (str): local database name
        - api (str): api to compare with (currently supported: oclc and loc )
        - return_mode (bool): indicate whether to return the authority dictionary

    Outputs:
        - {}_log (csv): log of all records checked
        - {}_inconsistencies (csv): csv file w/ wrong records
    '''
    try:
        # connect to database
        if api == "oclc":
            query = config.get("sql", "SQL_OCLC_QUERY").replace("\n", " ").replace("\'", "'")
        elif api == "loc":
            query =  config.get("sql", "SQL_LOC_QUERY").replace("\n", " ").replace("\'", "'")
        else:
            raise SyntaxError

        if api == "oclc":
            authority_tag = re.search('tag in \((\d+)', query).group(1)
            assert USER_DEFINED_TAG == authority_tag
        
        if api == "loc":
            # get all tags after the "tag in "
            # source for this regex: https://stackoverflow.com/questions/26176812/regex-match-for-number-within-parenthesis-separated-by-comma
            authority_tags = re.search('tag in \((\d+(?:,\s*\d+)*)\)', query).group(1).replace(' ', '').split(',')
            for authority_tag in authority_tags:
                # check for each loc tag that
                assert USER_DEFINED_TAG[-2:] == authority_tag[-2:]
        
        # add a limit to the query
        if limit != 'all':
            query += " limit {} ".format(batch_size)

        print("")
        print("Your {} SQL query: {}".format(api, query))
        print("")
        if api == "oclc":
            print("Comparing subfields {} in tag {} with tag {}".format(USER_DEFINED_SUBFIELDS, USER_DEFINED_TAG, authority_tag))
        else:
            print("Comparing subfields {} in tag {} with tag(s) {}".format(USER_DEFINED_SUBFIELDS, USER_DEFINED_TAG, authority_tags))
        print("")

        connection, cursor = connect_to_database(usr, pwd, hst, db, query)

        # fetch marc data from local database
        print('... fetching MARC data from local database')
        local_marc = fetch_data(cursor) # list with current data
        connection.close()

        # compare names
        print('... comparing subfields')
        authority_dict = {} # dictionary with authority record information
        # define log and inconsistencies csv names w/timestamps
        mdy = datetime.now().strftime("%m%d%y")
        uid = uuid.uuid1()
        log_path = "outputs/{}_{}_{}_log".format(mdy, api, uid)
        inconsistencies_path = "outputs/{}_{}_{}_inconsistent.csv".format(mdy, api, uid)
        # create inconsistencies csv with uchicago specific data
        with open(inconsistencies_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(['bib_id', 'tag', 'subfield', 'uchicago_name', 'authority_name', 'language', 'location'])
        # iterate over records, update authority dictionary and create logs
        max_records_per_log = 500000
        process_data(local_marc, max_records_per_log, authority_dict, log_path, inconsistencies_path, api)

        if return_mode:
            return authority_dict

    except AssertionError as e:
        print("[!] Non-valid tag comparison: {} vs {}".format(USER_DEFINED_TAG, authority_tag))
    except AttributeError as e:
        print("[!] Non-valid query")
    except SyntaxError as e:
        print("[!] Invalid API name, ", e)
    except Exception as e:
        print("Unexpected main program error:", e)
    

def create_oclc_session(key, scrt, ppid, pidns):
    '''
    Create an OCLC session via an access token

    For further reference, please see https://bookops-cat.github.io/bookops-worldcat/ and
    https://www.oclc.org/developer/develop/authentication/user-level-authentication-and-authorization.en.html

    Inputs:
        - key (str): WorldCat Key
        - scrt (str): secret
        - ppid (str): principal id
        - pidns (str): principal idns
    '''
    token = WorldcatAccessToken(
            oauth_server="https://oauth.oclc.org",
            key=key,
            secret=scrt,
            options={
                "scope": ["WorldCatMetadataAPI"],
                "principal_id": ppid,
                "principal_idns": pidns
            },
            agent="my_app/version 1.0"
        )
    return MetadataSession(credentials=token)

def process_data(data, max_records, authority_dict, log_path, inconsistencies_path, api):
    '''
    Process data (compare + create log)

    Inputs:
        - data (lst): local library's MARC data
        - max_records (int): number of maximum records per log file (in csv format)
        - authority_dict (dict): empty authority record dictionary to be compiled
        - log_path (str): path to log file
        - inconsistencies_path (str): path to inconsistencies file
        - api (str): api to call

    Side effects: updates authority_dict

    '''
    idx = 0
    file_name = log_path + ".csv"
    tracker = 0

    # if we are using the oclc api, initiate a Metadata session
    session = False
    if api == "oclc":
        try:
            session = create_oclc_session(WC_KEY, SECRET, PRINCIPAL_ID, PRINCIPAL_IDNS)
        except Exception as e:
            print("[!] Unable to connect to OcLC: ", e)
    
    # iterate through records that were retrieved from local MARC table
    for i, record in enumerate(tqdm(data)):
        try:
            if i == tracker:
                # change file_name
                if idx > 0:
                    file_name = log_path + '_' + str(idx) + '.csv'
                # reset max_records tracker and idx for future file names
                idx += 1
                tracker += max_records
                # new file
                with open(file_name, "w", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(['timestamp', 'bib_id', 'tag', 'ord', 'authority_id', 'error_message'])
            # append to existing file
            with open(file_name, "a", newline="") as f:
                w = csv.writer(f)
                uri = record.get('authority_id')
                bib_id = record['bib_id']
                tag = record['tag']
                ordi = record['ord']
                try:
                    # check match, update authority dictionary and inconsistency csv
                    compare_subfields(record, authority_dict, inconsistencies_path, session)
                    w.writerow([datetime.now(), bib_id, tag, ordi, uri, ""])
                except Exception as e:
                    # keep track of these exceptions in log
                    try:
                        w.writerow([datetime.now(), bib_id, tag, ordi, uri, e])
                    except Exception as eb:
                        print("[!] Could not write to csv error: ", eb)
        except Exception as e:
            print("[!] Unexpected error:", e)
        

#@profile
def compare_subfields(local_d, authority_d, inconsistencies_path, session):
    '''
    Compares subfields between local library record and api xml record
    
    Inputs:
        - local_d (dict): a record as a dictionary
        - authority_d (dict): a dictionary that keeps track of authority names
        - inconsistencies_path (str): path to inconsistencies csv file
        - session (MetadataSession): worldcat matadata session, None if the api is the LOC
    
    Side effects: appends to {date}_inconsistent.csv
    '''
    # fetch from API content or update authority dictionary
    authority_content = fetch_authority_content(local_d['authority_id'], authority_d, session)
    
    ## TO DO: DO STRIP MORE EFFICIENTLY!
    # append to csv
    with open(inconsistencies_path, "a", newline="") as f:
        w = csv.writer(f)
        for sf, lst_content in local_d['marc'].items():
            for content in lst_content:
                try:
                    if sf != '0':
                        # step 1: strip punctuation and accents
                        local_sf = strip_punct(content)
                        try: #handle when sf does not exist in authority
                            authority_sf_lst = []
                            for authority_sf in authority_content[0][sf]:
                               authority_sf_lst.append(strip_punct(authority_sf))
                        except Exception as nonloc:
                            authority_sf = '{} does not exist in authority'.format(nonloc)
                        # step 2: compare
                        if local_sf not in authority_sf_lst:
                            #current_inconsistencies[sf] = [uchicago_sf, loc_sf]
                            w.writerow([local_d['bib_id'], local_d['tag'], sf, local_sf, authority_sf_lst,
                                        local_d.get('language'), local_d.get('location')])
                        else:
                            continue
                except Exception as e:
                    print("[!] Unexpected error in compare_subfields(): ", local_d, e)


def fetch_authority_content(authority_id, authority_dict, session):
    '''
    Fetches authority file content. If authority key exists in the authority dictionary,
    it returns the content, else it calls the loc API, parses the xml and updates the
    authority dictionary.

    Inputs:
        - authority_id (str): a string with the an authority key (ie. loc uri or oclc number)
        - authority_dict (dict): contains subfield 0 and local MARC data
        - session (MetadataSession): worldcat matadata session, None if the api is the LOC

    Outputs:
        - authority_content (dict): dictionary w/ content for the authority file
    
    Side effects: updates authority dictionary
    '''
    # fetch authority_content from our tracked dictionary
    authority_content = authority_dict.get(authority_id)
    # if authority_content is None, we need to call the API
    if not authority_content:
        if session:
            # sleep one sec between oclc requests
            time.sleep(1)
            authority_id = str(authority_id)
            r = session.get_record(oclc_number=authority_id)
        else:
            # sleep T between requests (recommended 3)
            time.sleep(T)
            # loc
            xml_uri = get_marc_xml(authority_id) # get xml url
            r = requests.get(xml_uri) # GET request to LOC API
        root = ET.fromstring(r.text) # get text
        authority_content = fetch_authority_names(root) # store content
        authority_dict[authority_id] = authority_content # update dictionary
    
    return authority_content


def fetch_data(uchicago_cursor):
    '''
    Fetches data from a cursor resulting from a query to UChicago's OLE database.

    Inputs:
        - uchicago_cursor (obj): a cursor object

    Outputs:
        - data (dict): dictionary of dictionaries with subfield data for a given field
    '''
    data = []
    results = uchicago_cursor.fetchall()
    columns = [col[0] for col in uchicago_cursor.description]
    len_cols = len(columns)

    # iterate over rows
    for i, row in enumerate(results):
        try:
            # this results from the predefined query
            if len(row) == len_cols:
                # initialize dictionary
                temp_dict = dict(zip(columns, row))
            else:
                print("[!] Length mismatch: record has ", len(row), " attributes, expected ", len_cols)
                continue
            # extract fields from heading
            sf_dict = extract_subfields(temp_dict['heading'])
            # add uri
            # extract info and initialize in own dictionary
            if api == 'loc':
                try:
                    temp_dict['authority_id'] = sf_dict.get('0', None)[0]
                except Exception as e:
                    print("[!] 0 sf does not exist")
            elif api == 'oclc':
                temp_dict['authority_id'] = temp_dict.get('oclc', None)
            temp_dict['marc'] = sf_dict
            data.append(temp_dict)
        except Exception as e:
            print('[!] Could not fetch data from local database', row, e)
    
    return data

def extract_subfields(a_string, USER_DEFINED_SUBFIELDS=USER_DEFINED_SUBFIELDS):
    '''
    Extracts relevant fields for posterior comparison.
    
    Inputs:
        - a_string (str): concatenated string with subfields resulting from SQL query
    
    Outputs:
        - result (dict): a dictionary with subfields
    '''
    # split into subfields
    subfields = re.split(r"[\$]", a_string)[1 : ]
    # add subfield 0
    USER_DEFINED_SUBFIELDS.append('0')
    result = fetch_subfields(subfields, USER_DEFINED_SUBFIELDS, is_xml=False)

    return result


def fetch_subfields(subfields, check_lst, is_xml=True):
    '''
    Fetch subfields from a 100 tag.

    Inputs:
        - subfields (lst/dict): a list or dictionary with subfields
        - is_xml (bool): a boolean that defaults to True if the input is a MARC xml;
            if it isn't it will assume that a list of strings, each starting with the
            tag is being fed (e.g. subfields  = ["aName,", "qFuller Name,", ])
    
    Outputs: 
        - result (dict): a dictionary with subfields for a given tag; each subfield
            will have a list
    '''
    result = {}

    for sf in subfields:
        if is_xml:
            # this is from LOC's xml structure
            subfield = sf.attrib['code']
            sf_text = sf.text
        else:
            # this is for results of local library's query
            subfield = sf[0]
            sf_text = sf[1:]

        if subfield in check_lst:
            if result.get(subfield):
                # if the subfield exists, append the text to the list
                result[subfield].append(sf_text)
            else:
                # create a list with the subfield text in it
                result[subfield] = [sf_text]


    return result

# functions to get the marc loc record

def get_marc_xml(uri):
    '''
    Given a URI leading to an LC Name Authority File (LCNAF), returns a URL leading to the MARC xml
    
    Inputs:
        - uri (str): a uri

    Outputs:
        - marcxml (str): a uri for the corresponding loc marcxml file
    '''
    # remove commas from uris
    if ',' in uri:
        #print("wrong uri ", uri)
        uri = uri.replace(",", "")
    marcxml = uri + ".marcxml.xml"

    return marcxml

def fetch_authority_names(root, loc_tag='100'):
    '''
    Given an xml ET tree object, retrieve name from 100 tag
    
    Inputs:
        - root (obj): an xml root object

    Outputs:
        - content (lst): a list with a 100 tag dictionary of subfields
    '''
    try:
        # iterate through root object for children with the datafield tag
        for child in root.iter("{http://www.loc.gov/MARC21/slim}datafield"):
            # get appropriate tag
            if child.attrib['tag'] == USER_DEFINED_TAG:
                # get subfields
                result_100 = fetch_subfields(child, USER_DEFINED_SUBFIELDS)
    except Exception as e:
        print("[!] XML fetching error: ", e)

    content = [result_100]
    
    return content

def strip_punct(txt):
    '''
    Strips punctuation from a string

    Inputs:
        - txt (str): a string

    Outputs:
        - result (str): a string without punctuation nor special characters
    '''
    result = udc.unidecode(txt).translate(str.maketrans('', '', string.punctuation))
    return result

def connect_to_database(usr, pwd, hst, db, query):
    '''
    Connects to MySQL database and returns data from a query

    Inputs:
        - usr (str): OLE database user
        - pwd (str): OLE database password
        - hst (str): OLE database host
        - db (str): database
    
    Outputs: 
        - connection (obj): a mysql connection
        - cursor (obj): a mysql cursor with query results
    '''
    # open connection
    connection = mysql.connector.connect(user=usr,
                                password=pwd,
                                host=hst,
                                database=db,
                                charset='utf8',
                                )
    cursor = connection.cursor()
    cursor.execute(query)

    return connection, cursor


if __name__ == "__main__":

    api = sys.argv[1]
    batch_size = sys.argv[2]

    compare_records(api=api, limit=batch_size, return_mode=False)

