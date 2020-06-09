# Authority Compare
A tool that compares a library's local MARC table against OCLC or LOC MARC authority data.

Disclaimer: XYZ

## Motivation
UChicago's Library has been working on linking names with standard identifiers (URIs) to enhance user experience. This is achieved by using MarcEdit to batch process the existing records and link them to the Library of Congress’ (LOC) Name Authority File (NAF).

This tool compares headings in the 100, 600 and 700 fields of the local MARC table with headings in the 100 field in the LOC's NAF. It also compares headings in the 100 fields of the local MARC table with headings in the 100 fields of OCLC's Worldcat Metadata API and returns a report flagging inconsistent records as well as a log file.

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
### Defining global information
Fill in any user and database specific information in ```compare_config.ini```. 

Specify your local database's information in the ```[local]``` section like:
```
USER = your_user
PASSWORD = your_password
HOST = database_host_information
DATABASE = database_name
```

Specify the subfields you would like to compare in ```[subfields]``` separated by commas.

Specify your SQL queries depending on the API in ```SQL_OCLC_QUERY``` or/and ```SQL_LOC_QUERY```. You will need to extract the following fields for each record from your local database; all fields are required unless otherwise stated:
- bib_id: a bib id
- tag: a field
- ord: an ordinal
- heading: the subfield content of the marc record separated by $ (e.g. "$aMcKee, Edwin D.,$d1906-1984")
- language: (optional)
- location: (optional)

If the api is OCLC, you will also need the following field:
- oclc: an oclc number

Put down your OCLC credentials in the ```[oclc]``` section. You don't need credentials when you want to compare with the LOC API.

### Running the tool
After filling in your information in ```compare_config.ini```, you may run the project from your shell (e.g. bash or powershell). Navigate to ```src/``` and run the following command:

```
python compare.py [api_name] [number_of_records]
```

Here are a couple examples of how to use the program:

- Compare your local database with the LoC's API for the first 100 records of your query.
``` 
python compare.py loc 100
```
- Compare your local database with OCLC's API for all records of your query. If your 
``` 
python compare.py oclc all
```

Note that the API (oclc or loc) should always be specified and the maximum number of records must be specified as an integer or ```all```.

### Looking at your results
Your log and report of inconsistencies will appear in the ```outputs/``` folder with the following structure:

INSERT PIC HERE?

## Acknowledgements

## License