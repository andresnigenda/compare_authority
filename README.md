# Authority Compare
A tool that compares a library's local MARC table against OCLC or LOC MARC authority data.

## Motivation
UChicago's Library has been working on linking names with standard identifiers (URIs). This is achieved by using MarcEdit to batch process the existing records and link them to the Library of Congress’ (LOC) Name Authority File (NAF).

 This tool was designed to assist in identifying updated/inconsistent headings and thus contribute to the robustness of the library's linked data. It compares headings in the fields of the local MARC table with headings in the LOC's NAF API or OCLC's Worldcat Metadata API. The tool returns a report flagging inconsistent records as well as a log file.

## Prerequisites
This guide assumes that:
- *You have access to your library's SQL database*. UChicago's MARC table database is housed in a MySQL database, from which we extract the records we want to compare.
- *You have working knowledge of SQL queries*. You will need extract data from your own MARC table via SQL queries.
- *You have a basic understanding of the terminal and a programming language*. These are not necessary, but will make any necessary modifications so this tool works for your database easier to implement.

This tool runs on python 3.x, any further requirements are specified in ```requirements.txt``` and may be installed via ```pip install```.

## Repository structure

```
.
├── README.md                         
├── .gitignore
├── requirements.txt         
└── src/
    ├── compare.py
    ├── compare_config.ini
    └── outputs/
```

## Usage
You will want to clone or fork this project in order to run the program.

As of this iteration, this tool allows you to:
- Compare the text content of the subfields in any given tags in your database with the LOC NAF's corresponding valid tag (e.g. 100, 600, 700 vs 100; 650 vs 150).
-  Compare the text content of the subfields in a given tags in your database with the OCLC Worldcat Metadata API's corresponding valid tag (e.g. 100 vs 100, 600 vs 600).

### Defining user specific information

You will need to create a text file named ```passwords.ini``` in the ```src/``` directory. Paste and fill the following text and subsitute your credentials. If you are not using the OCLC API, you may skip the ```[oclc]``` section; you don't need credentials when you want to compare with the LOC API.

```
[oclc]
WC_KEY = your_wc_key
SECRET = your_secret
PRINCIPAL_ID = your_principal_id
PRINCIPAL_IDNS = your_principal_idns

[local]
USER = your_user
PASSWORD = your_password
HOST = database_host_information
DATABASE = database_name
```

How to lookup your OCLC idns and id: https://help.oclc.org/Metadata_Services/WorldShare_Collection_Manager/Troubleshooting/How_do_I_set_up_Marc_Edit_OCLC_Integration

### Defining subfields, queries and tags
Replace the relevant information in ```compare_config.ini```. Sample queries are provided.

Specify the subfields you would like to compare for your tags in the ```[subfields]``` section separated by commas.

Specify your API specific SQL queries depending on the API in ```SQL_OCLC_QUERY``` or/and ```SQL_LOC_QUERY```. You will need to extract the following fields for each record from your local database; all fields are required unless otherwise stated:
- bib_id: a bib id
- tag: a field
- ord: an ordinal
- heading: the subfield content of the marc record separated by "$" (e.g. "$aMcKee, Edwin D.,$d1906-1984")
- language: the language of the holding (optional)
- location: the physical location of the particular record (optional)

If the api is OCLC, you will also need the following field from your database:
- oclc: an oclc number

### Running the tool
You may run the tool from your shell (e.g. bash or powershell). If you are running this on a Windows computer you might want to consider installing Anaconda, which comes with a convenient Anaconda powershell prompt.

Navigate to ```src/``` and run the following command:

```
python compare.py [api_name] [number_of_records]
```

Where ```api_name``` is either "loc" or "oclc" and ```number_of_records``` is an integer or "all".

Here are a couple examples of how to use the program:

- Compare your local database with the LoC's API for the first 100 records of your query.
``` 
python compare.py loc 100
```
- Compare your local database with OCLC's API for all records of your query. If your 
``` 
python compare.py oclc all
```

### Checking your results
Your log and report of inconsistencies will appear in the ```outputs/``` folder with the following information: 
- log: bib_id, tag, subfield, uchicago_name, authority_name, language, location
- report: timestamp, bib_id, tag, ord, authority_id, error_message

## Acknowledgements
This tool was developed as part of the Hanna Holborn Gray Graduate Fellowship for Linked Data Management.

## License