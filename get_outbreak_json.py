# -*- coding: utf-8 -*-
"""
Created on Wed Apr  8 16:07:04 2020

@author: holmeschang
"""

import datetime
import numpy as np
import os
from six.moves import cPickle

import requests
from bs4 import BeautifulSoup

import json
from scipy.interpolate import UnivariateSpline
import matplotlib.pyplot as plt


URL = 'https://www.outbreak.my/states'
SAVEDIR = 'covid_data'


def find_text_enclosed(source,lower_target,upper_target,start_idx):
    lower = source.find(lower_target,start_idx)
    upper = source.find(upper_target,lower+len(upper_target))
    
    return source[lower+len(lower_target):upper]
   
def find_state_count(source,state_idx,ele_info):    
    state = find_text_enclosed(ele_info,'text: ',',',state_idx).strip("'")
    data = find_text_enclosed(ele_info,'data: [','],',state_idx).split(',')
    data = [int(x) for x in data]
    
    return (state,data)

def read_stats(name):
    state_total_daily = np.asarray(stat_dict[name])
    state_new_daily = np.asarray([0] + new_cases_daily[name])   
    
    return (state_total_daily,state_new_daily)

def process_stat_no_smooth(stats_total,stats_daily):
    daily_new_padded = np.concatenate((np.zeros(6,),stats_daily))
    weekly = np.convolve(daily_new_padded,np.ones(7,dtype=int),'valid')
    return (stats_total,weekly)
    
def process_stat(stats_total,stats_daily):
    stats_daily = stats_daily.astype(np.float32)
    stats_total =  stats_total.astype(np.float32)
    def check_continuos_point(x):

        for i in range(x.size):
            idx = np.where(x==x[i])[0]
            if idx.size > 1:
                c = 0.00001
                for i in idx[1:]:
                    x[i] += c
                    c += 0.00001

        return x
            
    stats_total =  check_continuos_point(stats_total)

    daily_new_padded = np.concatenate((np.zeros(6,),stats_daily))
    weekly = np.convolve(daily_new_padded,np.ones(7,dtype=int),'valid')
    xnew = np.linspace(stats_total.min(), stats_total.max(), stats_total.size)

    spl = UnivariateSpline(stats_total, weekly, k=3)
    weekly_smooth = spl(xnew)    
    
    return (xnew,weekly_smooth)

def scrap_outbreak():
    if not os.path.exists(SAVEDIR):
        os.makedirs(SAVEDIR)
    
    page = requests.get(URL)
    soup = BeautifulSoup(page.content, 'html.parser')
    
    ele = soup.find_all(name='script')
    ele_info = str(ele[9].extract()) 
    

    # Looking for text starting index for each state
    i = 0
    idx_state = []
    while i>=0:
        if i == 0:
            i = ele_info.find('chartOptionsState',0)
        else:
            i = ele_info.find('chartOptionsState',i+len('chartOptionsState'))
    
        if i >= 0:
            idx_state.append(i)
            
    idx = np.arange(0,len(idx_state),2)
    idx_state = np.array(idx_state)[idx][0:-2]  # last two is not state    
    
    # Looking for date label
    date = find_text_enclosed(ele_info,'data_date = [','];',0).strip().strip('\t').replace(' ','').split()
    date = ''.join(date).split(',')
    date = [da.strip("'") for da in date]
    
    # Looking for state name and count
    i = 0
    stats = [find_state_count(ele_info,state_idx,ele_info) for state_idx in idx_state]
    
    # Saving results in dictionary
    stat_dict = {}
    new_cases_daily = {}
    for stat in stats:
        stat_dict[stat[0]] = stat[1]
        new_cases_daily[stat[0]] = [x for x in np.asarray(stat[1],dtype=np.int32)[1:] - np.asarray(stat[1],dtype=np.int32)[0:-1]]
    
    
    # Save result to local file (save keep purpose)
    name = os.path.join(SAVEDIR,datetime.datetime.now().strftime('%Y%m%d%H%M%S') + '.neuon')
    with open(name,'wb') as fid:
        cPickle.dump(stat_dict,fid,protocol=cPickle.HIGHEST_PROTOCOL)
        cPickle.dump(new_cases_daily,fid,protocol=cPickle.HIGHEST_PROTOCOL)
        cPickle.dump(date,fid,protocol=cPickle.HIGHEST_PROTOCOL)
        
    return (stat_dict,new_cases_daily,date)

def generate_json(stat_dict,new_cases_daily,date,generate_curve):
    state_names = [key for key,value in stat_dict.items()]
    
    all_stats = [read_stats(name) for name in state_names]
    processed_stats = [process_stat(s[0],s[1]) for s in all_stats]
    processed_stats_ori = [process_stat_no_smooth(s[0],s[1]) for s in all_stats]

    # sum all malaysia cases
    daily_sum = np.sum(np.asarray([value for key,value in stat_dict.items()]),axis=0)
    daily_new = np.sum(np.asarray([[0]+value for key,value in new_cases_daily.items()]),axis=0)

    malaysia_stats = process_stat(daily_sum,daily_new)
    malaysia_stats_ori = process_stat_no_smooth(daily_sum,daily_new)    

    jsondata = {}
    jsondata['Malaysia'] = []
    jsondata['Malaysia'].append({
            "overall_case" : ','.join([str(x) for x in malaysia_stats_ori[0]]),
            "overall_case_smooth" : ','.join([str(x) for x in malaysia_stats[0]]),
            "new_weekly_confirm_case" : ','.join([str(x) for x in malaysia_stats_ori[1]]),
            "new_weekly_confirm_case_smooth" : ','.join([str(x) for x in malaysia_stats[0]]),
            "date" : ','.join(date)
            })
    
    
    for i in range(len(state_names)):
    #i=0
        
        jsondata[state_names[i]] = []
        jsondata[state_names[i]].append({
                "overall_case" : ','.join([str(x) for x in processed_stats_ori[i][0]]),
                "overall_case_smooth" : ','.join([str(x) for x in processed_stats[i][0]]),
                "new_weekly_confirm_case" : ','.join([str(x) for x in processed_stats_ori[i][1]]),
                "new_weekly_confirm_case_smooth" : ','.join([str(x) for x in processed_stats[i][0]]),
                "date" : ','.join(date)
                })

    name = os.path.join(SAVEDIR,datetime.datetime.now().strftime('%Y%m%d%H%M%S') + '.json')    
    with open(name,'w') as fid:
        json.dump(jsondata,fid,indent=5)    

    if generate_curve:
        filename = os.path.join(SAVEDIR,datetime.datetime.now().strftime('%Y%m%d%H%M%S') + '_malaysia.png')

        plt.figure(figsize=(10,10)) 
        
        plt.plot(malaysia_stats_ori[0][1:],malaysia_stats_ori[1][1:],label='raw data')     
        plt.plot(malaysia_stats[0][1:],malaysia_stats[1][1:],label='smoothen data') 
        
        plt.plot(malaysia_stats_ori[0][1:],malaysia_stats_ori[1][1:],'ro')
        plt.yscale('log')
        plt.xscale('log')  
        plt.title('Malaysia Covid19 Trend')
        plt.legend(loc="upper left")
        plt.xlabel('Overall cases')
        plt.ylabel('New cases (weekly)')
        plt.tight_layout()    
        print(filename)
        plt.savefig(filename)   
        plt.close()
        
        filename = os.path.join(SAVEDIR,datetime.datetime.now().strftime('%Y%m%d%H%M%S') + '_states.png')
        plt.figure(figsize=(20,20)) 
        for ori_stat,name,stat,i in zip(processed_stats_ori,state_names,processed_stats,np.arange(len(state_names))):
            plt.subplot(4,4,i+1)
            
            plt.plot(ori_stat[0][1:],ori_stat[1][1:],label='raw data')     
            plt.plot(stat[0][1:],stat[1][1:],label='smoothen data') 
        
            plt.plot(ori_stat[0][1:],ori_stat[1][1:],'ro')
            plt.yscale('log')
            plt.xscale('log')  
            plt.title(name)
            plt.legend(loc="upper left")
            plt.xlabel('Overall cases')
            plt.ylabel('New cases (weekly)')
        plt.tight_layout()    
        print(filename)
        plt.savefig(filename)
        plt.close()


if __name__ == '__main__':
    stat_dict,new_cases_daily,date = scrap_outbreak()
    generate_json(stat_dict,new_cases_daily,date,generate_curve=True)
    
    
    
    