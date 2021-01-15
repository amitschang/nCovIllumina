#!/usr/bin/env python
"""
Script to prepare nextstrain alpha files
"""
###TODO
# Run_dir, file pattern given make multifasta files
# Take multifasta file and make nextstrain fake metadata
# NEXT_METADATA ( optional ) if provided check if fields are present and throw error if not 
#  (

# Assumptions : Second column sample_name is unique by itself and only the latest run for the sample is retained in submission manifest
#1) Get files in the submission manifest from seq_path 
#2) Exclude submitted files as GISAID will already have it
#3) Add submitted files to local build only
#4) If metadata exists use metadata
#5) Else create fake metadata for the non existing samples


import pandas as pd
import numpy as np 
import json , os
import argparse
import random , time
from datetime import datetime , date , timedelta
from pandas.io.json import json_normalize
import glob ,re , tempfile ,shutil
import random , time
from datetime import datetime , date , timedelta
from pyfaidx import Fasta
from datetime import date
import warnings
from pytz import timezone
from Bio import SeqIO
import yaml

warnings.simplefilter(action='ignore', category=FutureWarning)
pd.options.mode.chained_assignment = None  # default='warn'

DATE_FMT ="%Y%m%d"
SUB_FMT ="%Y-%m-%d"
REF_LENGTH = 29903
count_Ns = 5000
N_DAYS=14

CUR_DATE = datetime.now(timezone('US/Eastern'))
#SUB_DATE = self.CUR_DATE.strftime(self.SUB_FMT)
#CUR_DATE = self.CUR_DATE.strftime(self.DATE_FMT)

def log(message):
    """ Log messages to standard output. """
    print(time.ctime() + ' --- ' + message, flush=True)

def generate_date(n_days,date_fmt):
    """ Generate random date with in the last n days """
    end = datetime.now(timezone('US/Eastern'))
    start = end - timedelta(days=n_days)
    random_date = start + (end - start) * random.random()
    return random_date.strftime(date_fmt)

def prepare_metadata(sname_list, meta_dict, len_dict, pangolin_dict, next_dict, n_days, out_file ):
    """ Prepare metadata dict as per the config fields """
    meta_df = pd.DataFrame(columns = meta_dict.keys())
    samples = {'strain': sname_list}
    meta_df = meta_df.append(pd.DataFrame(samples))
    cur_date = datetime.now(timezone('US/Eastern'))
    for col in meta_df.columns:
        #if col == "strain":
        #   meta_df[col] = sname_list
        if col not in ["strain" , "pangolin_lineage" , "Nextstrain_clade" , "length", "date" , "date_submitted"]:
           meta_df[col] = meta_dict[col]
        if col == "pangolin_lineage":
           meta_df['pangolin_lineage'] = df['strain'].map(pangolin_dict)
        if col == "Nextstrain_clade":
           meta_df['Nextstrain_clade'] = df['strain'].map(next_dict)
        if col == "length":
           meta_df['length'] = df['strain'].map(len_dict)
        if col == "date":
           meta_df['date'] = [generate_date(n_days,cur_date) for i in range(1,len(sname_list))]
        if col == "date_submitted":
           meta_df['date'] = cur_date.strftime(date_fmt)
    meta_df.to_csv(out_file, mode='w', sep="\t",header=True)

def get_fasta_lengths(fasta):
    fa_lens = []
    N_counts = []
    for seq_record in SeqIO.parse(fasta, "fasta"):
        A_count = seq_record.seq.count('A')
        C_count = seq_record.seq.count('C')
        G_count = seq_record.seq.count('G')
        T_count = seq_record.seq.count('T')
        N_count = seq_record.seq.count('N')
        fa_lens.append(len(seq_record))
        N_counts.append(N_count)
    return fa_lens, N_counts

def getKeysByValues(dictOfElements, listOfValues):
    listOfKeys = list()
    listOfItems = dictOfElements.items()
    for item  in listOfItems:
        if item[1] in listOfValues:
           listOfKeys.append((item[1], item[0]))
    return  listOfKeys

def get_file_list(file_list,file_pattern):
    """
    get file list of consensus fasta from RUN_DIR and FASTA_PATH

    """
    c_list = []
    for i in file_list:
        cfile = glob.glob(i + file_pattern)[0]
        c_list.append(cfile)
    return c_list

def get_files_from_path(rundir,fasta_path,file_pattern):
    """
    get file list of consensus fasta from RUN_DIR and FASTA_PATH

    """
    c_list = []
    fullpath = os.path.join(rundir, fasta_path)
    file_list = glob.glob(fullpath + "/" + file_pattern )  # You may use iglob in Python3     
    assert file_list is not None, "Fasta Files with pattern {0} not present in {1}".format(file_pattern , fullpath)
    for i in file_list:
        cfile = glob.glob(i + file_pattern)[0]
        c_list.append(cfile)
    return c_list

def get_fasta_header(seq):
    """
    get header from fasta file
    """
    with open(seq,'r') as fd:
         header = []
         for line in fd:
             if line[0]=='>':
                header.append(line.strip().split(">")[1].split(" ")[0])
    return header

def parse_tsv(file,col=None):
    """ Parse tsv files into a pandas dataframe"""
    if col:
       df = pd.read_table(file,sep="\t",header=col,skip_blank_lines=True)
    else:
       df = pd.read_table(file,sep="\t",header=None,skip_blank_lines=True)
    log("INFO : Parsed number of rows :" +  str(df.shape[0]) + " , columns :" + str(df.shape[1]) )
    return df 

def parse_tsv_to_dict(file,col1, col2):
    """ Parse tsv files into a dict of 2 columns"""
    df = pd.read_table(file,sep="\t",header=0,skip_blank_lines=True) 
    vdict = dict(zip(df.col1, df.col2)) 
    return vdict

def parse_csv_to_dict(file,col1, col2):
    """ Parse tsv files into a dict of 2 columns"""
    df = pd.read_csv(file, sep=",",header=0,skip_blank_lines=True) 
    vdict = dict(zip(df.col1, df.col2)) 
    return vdict

def parse_yaml(file):
    """ Parse yaml file into a dict""" 
    try:
       print(file)
       with open(file) as f:
            return yaml.safe_load(f)  
    except:
       raise
 
def concat_fasta_files(fa_list, out):
    """
    Function to concat fasta files from a list
    """
    filt_fnames = []
    with open(out, 'w') as outfile:
       for fname in fa_list:
           ffile = glob.glob(fname)[0]
           g_lengths, n_counts = get_fasta_lengths(ffile)
           if g_lengths[0] < 25000 or n_counts[0] < 5000:
              filt_fnames.append(ffile)
              with open(ffile) as infile:
                 for line in infile:
                    outfile.write(line)
           else:
              log("INFO : Skipping {0} from alpha Genome Length :  {1} , N_counts : {2}".format(fname,g_lengths[0],n_counts[0]))
    return filt_fnames

def get_latest_file(path, *paths):
    """Returns the name of the latest (most recent) file 
    of the joined path(s)"""
    fullpath = os.path.join(path, *paths)
    list_of_files = glob.glob(fullpath)  # You may use iglob in Python3
    if not list_of_files:                # I prefer using the negation
        return None                      # because it behaves like a shortcut
    latest_file = max(list_of_files, key=os.path.getctime)
    _, filename = os.path.split(latest_file)
    return filename

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script to Parse new sequencing runs from alpha nextstrain")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-g",dest="FA_FILE",type=str, help="Path to the multifasta file")
    group.add_argument("--rundir",dest="RUN_DIR",type=str, help="Path to the sequencing runs folder")
    parser.add_argument("--fasta-path",dest="FASTA_PATH",type=str,help="Path to the draft consensus fasta folder")
    parser.add_argument("--file-pattern",dest="FASTA_PAT",type=str, default="complete.fasta", help="File pattern of fasta files")
    parser.add_argument("--metadata-config",dest="CONFIG_META",type=str, required=True, help="Path to a yaml file with standard metadata file")
    parser.add_argument("--next_meta",dest="NEXT_META",type=str, required=False, help="Path to a tsv file real metadata file for samples run")
    parser.add_argument("--pangolin_clade",dest="P_CLADE",type=str, required=False, help="Path to a csv file with pangolin clades")
    parser.add_argument("--nextstrain_clade",dest="NEXT_CLADE",type=str, required=False, help="Path to a tsv file nextstrain clades")
    parser.add_argument("--global-seq",dest="GLOBAL_SEQ",type=str, required=False, help="Path to a subsampled fasta file")
    parser.add_argument("--global-meta",dest="GLOBAL_META",type=str, required=False, help="Nextstrain metadata file for the subsampled fasta")
    parser.add_argument("-out",dest="OUTPUT_DIR",type=str, required=True, help="Path to output directory for alpha nextstrain")
    
    args = parser.parse_args()
    
    if bool(args.RUN_DIR) ^ bool(args.FASTA_PATH):
       parser.error('--rundir, --fasta-path must be given together')
    
    outdir = args.OUTPUT_DIR
     
    if not os.path.exists(outdir):
       os.makedirs(outdir)

    if args.FA_FILE:
       fasta = args.FA_FILE
       ## TODO : Check if any fasta file has n_counts > 5000  and length < REF_LEN if FA_FILE is provided
    else:
       # Make multifasta file
       fasta = os.path.join(outdir,"run_sequences.fasta")
       fa_file_list = get_files_from_path(rundir,fasta_path,file_pattern)
       concat_fasta_files(fa_file_list,fasta)
    
    sample_names = get_fasta_header(fasta) 
    glens , n_counts = get_fasta_lengths(fasta)
    glens_dict = zip ( sample_names, glens )

    if args.NEXT_META:
       next_metadata = args.NEXT_META
       # TODO: Check if fields match config or report error 
    else:
       ### Create fake metadata
       next_metadata = os.path.join(outdir,"run_sequences_metadata.tsv")
       if args.CONFIG_META:
          meta_fields = parse_yaml(args.CONFIG_META)
          print(meta_fields)
       # parse pangolin
       if args.P_CLADE:
          pangolin_dict = parse_csv_to_dict(args.P_CLADE,"taxon" , "lineage")
          print(pangolin_dict)
       else:
          log("WARNING : Pangolin  clade output file not provided; Set to ? for all samples " )
          pangolin_dict = dict(zip(sample_names,["?" for i in sample_names ])) 
          print(pangolin_dict)
       # parse nextstrain
       if args.NEXT_CLADE:
          next_dict = parse_tsv_to_dict(args.NEXT_CLADE,"name","clade") 
          print(next_dict)
       else:
          log("WARNING : Nextstrain clade output file not provided; Set to ? for all samples " )
          next_dict = dict(zip(sample_names,["?" for i in sample_names ])) 
          print(next_dict)
       log("INFO : Generating metadata for the samples " )
       prepare_metadata(sample_names, meta_fields, glens_dict, pangolin_dict, next_dict, N_DAYS, next_metadata)
       log("INFO : Done !!!")
