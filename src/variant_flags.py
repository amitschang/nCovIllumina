#!/usr/bin/env python

import sys
import numpy as np
import pandas as pd

from samtools_funcs import collect_position_pileup

def depth_near_threshold(depth,depth_threshold,coverage_flag):
    """
    Function that returns a depth flag string if the read depth at a position is
    within a pre-specified percentage of the depth threshold or lower
    """
    
    # get the coverage flag threshold
    frac = float(coverage_flag/100)
    highend = depth_threshold + (depth_threshold*frac)
    
    # check if coverage is close to depth threshold
    if depth<highend:
        return('depth near threshold')
    else:
        return(np.nan)


def minor_allele_freq(depth,alt_allele_freq,maf_flag):
    """
    Function that returns a MAF flag string if the cumulative minor allele frequency
    at a position is higher than a pre-specified value and indicates if the position
    is a candidate within host variant, or a potentially worrisome mixed position
    """
    
    # convert the flag thresholds to decimals
    maf = maf_flag/100.0
    
    # the case that there are no flags
    if alt_allele_freq<0.15 or alt_allele_freq>0.85:
        return(np.nan,np.nan)
    
    # if there are flags, distinguish between the isnv and mixed scenarios
    if 0.15<=alt_allele_freq<maf or (1-maf)<alt_allele_freq<=0.85:
        return('0.15<maf<%0.2f' % (maf),np.nan)
    elif maf<=alt_allele_freq<=(1-maf):
        return(np.nan,'mixed position')


def allele_in_ntc(pos,alt,depth,ntc_bamfile,snp_depth_factor):
    """ 
    Function that returns a flag string if the alternate allele is present in the negative control
    and the coverage in the sample is not more than snp_depth_factor * coverage in negative control
    """
    
    # print warning if there was no NTC used on this run
    if ntc_bamfile=="None":
        return('NTC=None')
    
    # get the pileup at this position in the negative control
    ntc_pileup = collect_position_pileup(ntc_bamfile, pos)
    
    if alt in ntc_pileup:
        # require coverage at this sample to be some multiple of the negative control
        if depth <= (snp_depth_factor * ntc_pileup[0]):
            return('allele in NTC')
    
    # if alt not in negative control or depth is high enough
    return(np.nan)


def new_variant(pos,ref,alt,global_vars,ns_snp_threshold):
    """
    Function that returns a flag string if a SNP has not been seen in published sequences
    Requires the SNP to be found in a specific number of published sequences
    to avoid confounding with SNPs that may be a result of sequencing errors in other samples
    """
    
    # read in the global diversity file as a dataframe
    # note: this only checks if a position has been mutated, not the mutation itself
    ns_snps = pd.read_csv(global_vars,sep='\t')
    ns_snps = ns_snps[['base','events']]
    
    # if the position has not been variable before, return false
    if pos not in ns_snps.base.values:
        return('not in nextstrain')
    
    # check if it has been found enough times
    else:
        tmp = ns_snps[ns_snps.base==pos]
        if int(tmp.events) >= ns_snp_threshold:
            return(np.nan)
        else:
            return('not in nextstrain')


def variant_caller_mismatch(supp_vec):
    """
    Function that returns a flag string if a variant has not been detected by all callers
    Currently assumes callers are: ivar, freebayes, samtools (in that order)
    """
    
    # return different codes for different mismatch strings
    if supp_vec == '111':
        return(np.nan)
    elif supp_vec == '100':
        return('mismatch(i)')
    elif supp_vec == '010':
        return('mismatch(f)')
    elif supp_vec == '001':
        return('mismatch(s)')
    elif supp_vec == '110':
        return('mismatch(i+f)')
    elif supp_vec == '101':
        return('mismatch(i+s)')
    elif supp_vec == '011':
        return('mismatch(f+s)')
    else:
        sys.exit('%s is not a valid support vector' % supp_vec)


def strand_bias_detected(info,alt,strand_threshold):
    """ 
    Function that returns a flag string if a variant is called unequally on the forward and reverse strands
    strandAF order is: positive alts, total positive reads, negative alts, total negative reads
    """
    
    pos_alleles = info['ILLUMINA_POSITIVE_STRAND_FREQUENCIES']
    neg_alleles = info['ILLUMINA_NEGATIVE_STRAND_FREQUENCIES']
    
    pos_alleles = [int(x) for x in pos_alleles.split(',')]
    neg_alleles = [int(x) for x in neg_alleles.split(',')]
    
    # get the alternate allele frequency on each strand
    idx = ['A','C','G','T','N','O'].index(alt)
    posAF = [float(pos_alleles[idx]/sum(pos_alleles)) if sum(pos_alleles)>0 else 0.0][0]
    negAF = [float(neg_alleles[idx]/sum(neg_alleles)) if sum(neg_alleles)>0 else 0.0][0]
    
    # get the strand counts on each strand
    strand_counts = [pos_alleles[idx],sum(pos_alleles),neg_alleles[idx],sum(neg_alleles)]
    strand_counts = "FWD:"+str(strand_counts[0])+"/"+str(strand_counts[1])+",REV:"+str(strand_counts[2])+"/"+str(strand_counts[3])
    
    strand_threshold = strand_threshold/100.0
    
    # compare frequencies to threshold
    if (posAF<strand_threshold) and (negAF<strand_threshold):
        return(np.nan,strand_counts) # no bias if both are low frequency
    elif posAF<strand_threshold:
        return('strand bias: low +AF',strand_counts)
    elif negAF<strand_threshold:
        return('strand bias: low -AF',strand_counts)
    else:
        return(np.nan,strand_counts) # no bias if both are high frequency


def ambig_in_key_position(pos,key_vars,masked_align,var_idx):
    """ 
    Function that returns a flag string if a position is at an important site
    but is an ambiguous base ('N') in the consensus genome
    """
    
    # load in key variants
    key_snps = pd.read_csv(key_vars,sep='\t',header=None,names=['pos'])
    key_snps = list(key_snps.pos.values)
    
    # no flag needed if this position is not one of the important ones
    if pos not in key_snps:
        return(np.nan)
    
    # if it is an important position
    else:
        if masked_align[1,var_idx]=='N':
            return('ambig in key position')
        else:
            return(np.nan)
        

def in_homopolymer_region(pos,homopolymers):
    """ 
    Function that reports if the position is in a known homopolymer region
    """
    
    # current homopolymer list
    homopolymers = pd.read_csv(homopolymers,sep='\t',header=None,names=['pos'])
    homopolymers = list(homopolymers.pos.values)
    
    if pos in homopolymers:
        return(True)
    else:
        return(False)
