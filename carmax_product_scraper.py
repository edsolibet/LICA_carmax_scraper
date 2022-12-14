# -*- coding: utf-8 -*-
"""
Created on Wed Aug 10 09:47:37 2022

@author: carlo
"""
import pandas as pd
import numpy as np
import re, os
from datetime import datetime
import datetime as dt
import time
import gspread
from pytz import timezone

import streamlit as st
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from st_aggrid import GridOptionsBuilder, AgGrid

# to run selenium in headless mode (no user interface/does not open browser)
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument("--disable-gpu")
options.add_argument("--disable-features=NetworkService")
options.add_argument("--window-size=1920x1080")
options.add_argument("--disable-features=VizDisplayCompositor")

# set timezone
phtime = timezone('Asia/Manila')

def get_last_page(driver, url_dict):
    '''
    Get last page of used cars list
    '''
    driver.get(url_dict['url'])
    page = driver.find_elements(By.XPATH, url_dict['xpath'])
    return max([int(page[i].text) for i in range(len(page)) if page[i].text.isnumeric()])

def get_re_match(list_, info_type):
    if info_type == 'price':
        price = [float(''.join(re.search('^P[0-9]*,?[0-9]*,?[0-9]{3}?', p).group(0)[1:].split(',')))
                 for p in list_ if re.search('^P[0-9]*,?[0-9]*,?[0-9]{3}?', p) is not None]
        return price
    elif info_type == 'car':
        cars = [car for car in list_ if re.search('^P[0-9]*,?[0-9]*,?[0-9]{3}?', car) is None]
        return cars
    elif info_type == 'mileage':
        return [float(''.join(m[:-3].split(','))) for m in list_[0::3]]
    elif info_type == 'transmission':
        return list_[1::3]
    elif info_type == 'fuel':
        return list_[2::3]

def mileage_bracket(mileage):
    if mileage is not None:
        if mileage <= 15000:
            return '0-15,000 km'
        elif (mileage >= 15000) and (mileage < 30000):
            return '15,000-30,000 km'
        elif (mileage >= 30000) and (mileage < 60000):
            return '30,000-60,000 km'
        elif (mileage >= 60000) and (mileage < 100000):
            return '60,000-100,000 km'
        else:
            return '>100,000 km'
    else:
        return ''

@st.experimental_memo
def autodeal_scrape(_driver):
    car_list, price_list, info_list = list(), list(), list()
    last_page = get_last_page(driver, site_last_page['autodeal'])
    mybar = st.progress(0)
    for page in range(1, last_page+1):
        # all brands url
        url_page = 'https://www.autodeal.com.ph/used-cars/search/certified-pre-owned+repossessed+used-car-status/page-' + str(page) + '?sort-by=relevance'
        print("Getting info from Page: {}".format(page))
        driver.get(url_page)
        # find elements via xpath
        cars = driver.find_elements(By.XPATH, '//h3')
        price = driver.find_elements(By.XPATH, '//h4')
        info = driver.find_elements(By.XPATH, '//span[contains(@class,"small reducedopacity")]')
        # try-except to handle exceptions
        for i in range(len(info)):
            try: 
                info_list.append(info[i].text)
            except:
                continue
        for c in range(len(cars)):
            try:
                car_list.append(cars[c].text)
            except:
                continue
        for p in range(len(price)):
            try:
                price_list.append(price[p].text)
            except:
                continue
        mybar.progress(round((page-1)/last_page, 2))
    mybar.empty()
    cars = get_re_match(car_list, 'car')
    price = get_re_match(price_list, 'price')
    mileage = get_re_match(info_list, 'mileage')
    transmission = get_re_match(info_list, 'transmission')
    fuel = get_re_match(info_list, 'fuel')
    df_ad = pd.DataFrame(list(zip(cars, transmission, mileage, fuel, price)), 
                         columns=['model', 'transmission', 'mileage', 'fuel_type', 'price'])
    df_ad.insert(2, 'year', df_ad.loc[:, 'model'].apply(lambda x: int(x[:5].strip())))
    df_ad.insert(1, 'make', df_ad.loc[:, 'model'].apply(lambda x: x.split(' ')[1]))
    df_ad.loc[:,'mileage'] = df_ad.apply(lambda x: mileage_bracket(x['mileage']), axis=1)
    #df_ad.loc[:, 'model'] = df_ad.loc[:, 'model'].apply(lambda x: ' '.join(x.split(' ')[2:]))
    #df_ad.loc[:, 'model'] = df_ad.loc[:, 'model'].apply(lambda x: re.split('[AM(CV)].?T', x)[0].strip() if re.search('[AM(CV)].?T', x) is not None else x)
    df_ad.loc[:, 'platform'] = 'autodeal'
    return df_ad

@st.experimental_memo
def automart_scrape(_driver):
    
    def fix_mileage(x):
        return ''.join(x[:-3].split(','))
    
    car_list, price_list, info_list = list(), list(), list()
    last_page = get_last_page(driver, site_last_page['automart'])
    print('Last page: {}'.format(last_page))
    mybar = st.progress(0)
    for page in range(1, last_page+1):
        # all brands url
        url_page= site_last_page['automart']['url']
        print("Getting info from Page: {}".format(page))
        driver.get(url_page)
        # find elements via xpath
        cars = driver.find_elements_by_xpath('//h4')
        price = driver.find_elements_by_xpath('//h5')
        info = driver.find_elements_by_xpath('//td')
        # try-except to handle exceptions
        for c in range(len(cars)):
            try:
                car_list.append(cars[c].text)
            except:
                continue
        for p in range(len(price)):
            try:
                price_list.append(price[p].text)
            except:
                continue
        for i in range(len(info)):
            try:
                info_list.append(info[i].text)
            except:
                continue
        print ('Obtained {} cars'.format(len(car_list)))
        mybar.progress(round((page-1)/last_page, 2))
    mybar.empty()
    trans_list = [info_list[t*4] for t in range(int(len(info_list)/4))]
    dist_list = [info_list[4*t+1] for t in range(int(len(info_list)/4))]
    fuel_list = [info_list[4*t+2] for t in range(int(len(info_list)/4))]
    am_df = pd.DataFrame(list(zip(car_list, trans_list, fuel_list, dist_list, price_list)), columns = ['model', 'transmission', 'fuel_type', 'mileage', 'price'])
    am_df.insert(2, 'year', am_df.loc[:, 'model'].apply(lambda x: int(x[:4].strip())))
    am_df.insert(1, 'make', am_df.loc[:, 'model'].apply(lambda x: x[5:].split(' ')[0].strip()))
    # am_df.loc[:, 'model'] = am_df.loc[:, 'model'].apply(lambda x: ' '.join(x[5:].split(' ')[1:]).strip())
    am_df.loc[:, 'mileage'] = am_df.loc[:,'mileage'].apply(lambda x: mileage_bracket(float(fix_mileage(x))) if fix_mileage(x).isnumeric() is not False else 0)
    am_df.loc[:, 'price'] = am_df.loc[:,'price'].apply(lambda x: float(''.join(x[2:].split(','))))
    trans_dict = {'AT': 'Automatic', 'MT': 'Manual', 'CVT': 'CVT'}
    am_df.loc[:,'transmission'] = am_df.loc[:,'transmission'].apply(lambda x: trans_dict[x])
    am_df.loc[:, 'platform'] = 'automart'
    return am_df

def cm_search_price(x):
    pattern = '(\d(\.)?\d*\sMillion)|(\d*,?\d+)'
    return re.search(pattern, x)

def mileage_str_to_num(x):
    search = re.search('[0-9]*,?[0-9]*,?[0-9]{3}', x)[0]
    return float(''.join(search.split(',')))

def extract_fuel_type(x):
    search = re.search('Gasoline|Diesel|Lpg', x)
    return search

def cleanup_info(x):
    # Get index for transmission data
    if re.search('[AM(CV)].?T', x) is not None:
        for match in re.finditer('[AM(CV)].?T', x):
            trans_index_s = match.start(0)
            trans_index_e = match.end(0)
    else:
        trans_index_s = None
        trans_index_e = None
    # Get index for fuel_type data
    if re.search('Gasoline|Diesel|Lpg', x) is not None:
        for match in re.finditer('Gasoline|Diesel|Lpg', x):
            fuel_index = match.end(0)
    else:
        fuel_index = None
    # Remove fuel and transmission data from info, and ", "
    return (x[fuel_index:trans_index_s].strip()[2:])[trans_index_e:]

def cleanup_price(x):
    if re.search('Million', x) is not None:
        for m in re.finditer('Million', x):
            return float(x[:m.start(0)-1])*1000000
    else:
        return float(''.join(x.split(',')))

@st.experimental_memo
def carmudi_dataframe(scrape_list):
    car_list, info_list, price_list = scrape_list
    
    # Setup DataFrame
    df_cm = pd.DataFrame(zip(car_list, info_list, price_list), columns=['car', 'info', 'price'])
    # car info
    df_cm.insert(0, 'make', df_cm.loc[:, 'car'].apply(lambda x: x.split(' ')[1].strip() if (len(x.split(' ')) > 1) else x.strip()))
    df_cm.insert(1, 'model', df_cm.loc[:, 'car'].apply(lambda x: ' '.join(x.split(' ')[2:]).strip()))
    df_cm.insert(2, 'year', df_cm.loc[:, 'car'].apply(lambda x: int(x[:4].strip())))
    # price
    df_cm.loc[:, 'price'] = df_cm.loc[:,'price'].apply(lambda x: cleanup_price(x))
    # info
    df_cm.insert(3, 'transmission', df_cm.loc[:,'info'].apply(lambda x: re.search('[AM(CV)].?T', x)[0] if re.search('[AM(CV)].?T', x) is not None else np.NaN)) 
    df_cm.insert(4, 'fuel_type', df_cm.loc[:,'info'].apply(lambda x: extract_fuel_type(x)[0] if extract_fuel_type(x) is not None else np.NaN))
    df_cm.insert(5, 'mileage', df_cm.loc[:,'info'].apply(lambda x: mileage_bracket(mileage_str_to_num(x)) if re.search('.*[0-9]*KM', x) is not None else np.NaN))
    df_cm.loc[:, 'platform'] = 'carmudi'
    # df_cm.loc[:, 'info'] = df_cm.loc[:,'info'].apply(lambda x: cleanup_info(x))
    # drop info feature
    df_cm = df_cm.drop(['info', 'car'], axis=1)
    
    return df_cm

@st.experimental_memo
def carmudi_scrape(_driver):
    url_page = 'https://www.carmudi.com.ph/used-cars/'
    driver.get(url_page)
    
    try:
        exit_select_city = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, '//a[@href="javascript:void(0)"]/i[@class="icon-close close__city"]')))
        exit_select_city.click()
        print ("Exited city select")
    except:
        pass
    
    
    car_list, price_list, info_list = list(), list(), list()
    #last_height = driver.execute_script("return document.body.scrollHeight")
    last_height = driver.execute_script("return document.documentElement.scrollHeight")
    print ('last height: {}'.format(last_height))
    mybar = st.progress(0)
    num_cars = int(driver.find_element(By.XPATH, '//*[contains(text(), "Used Cars available for sale in the Philippines")]').text.strip().split(' ')[0])
    while True:
        #driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
        print ("Scrolling..")
        time.sleep(2)
        new_height = driver.execute_script("return document.documentElement.scrollHeight")
        print ("new_height: {}".format(new_height))
        try:
            load_more_btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, '//div[@class="d-flex justify-content-center"]/a[@href="javascript:void(0)"]')))
            load_more_btn.click()
            print ('Clicked Load More')
        except:        
            if new_height == last_height:
                print ("Finished scrolling!")
                break
            else:
                pass
        last_height = new_height
        mybar.progress(round((new_height/100)/num_cars, 2))
    mybar.empty()
    info = driver.find_elements_by_css_selector('p.shortDescription')
    cars = driver.find_elements_by_css_selector('a')
    price = driver.find_elements_by_css_selector('div.new__car__price')
    for i in range(min([len(info), len(price), len(cars)])):
        try: 
            info_list.append(info[i].text)
            car_list.append(cars[i].text)
            price_list.append(price[i].text)
        except:
            continue
        
    info_list = [x for x in info_list if re.search('Gasoline|Diesel|Lpg', x) is not None]
    car_list = [x for x in car_list if re.search('^[0-9]{4}\s.*', x) is not None]
    price_list = [cm_search_price(x)[0] for x in price_list if cm_search_price(x) is not None]
    print ("Found {} prices".format(len(price_list)))

    return [car_list, info_list, price_list]

def show_table(df):
    # table settings

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(min_column_width=8)
    gridOptions = gb.build()
    
    # selection settings
    AgGrid(
        df,
        gridOptions=gridOptions,
        data_return_mode='AS_INPUT', 
        update_mode='MODEL_CHANGED', 
        fit_columns_on_grid_load=False,
        autoSizeColumn = 'model',
        theme='blue', #Add theme color to the table
        enable_enterprise_modules=True,
        height=400, 
        reload_data=False)
    
@st.experimental_memo
def convert_csv(df):
    # IMPORTANT: Cache the conversion to prevent recomputation on every rerun.
    return df.to_csv().encode('utf-8')

@st.experimental_memo
def last_update_date():
    return datetime.today().strftime('%Y-%m-%d')

def update():
    st.experimental_memo.clear()
    st.experimental_rerun()


@st.experimental_memo
def write_to_gsheet(df, key):
    '''
    Creates new sheet in designated googlesheet and writes selected data from df
    
    Parameters
    ----------
    df: dataframe
        dataframe to write to google sheet
    
    '''
    credentials = {
      "type": "service_account",
      "project_id": "xenon-point-351408",
      "private_key_id": "f19cf14da43b38064c5d74ba53e2c652dba8cbfd",
      "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC5fe2N4yS74jTP\njiyv1EYA+XgnrTkZHwMx4ZY+zLuxx/ODPGxJ3m2e6QRUtz6yBUp1DD3nvzaMYY2d\nea6ti0fO2EPmmNIAZzgWVMOqaGePfXZPN1YN5ncLegZFheZuDrsz0/E+KCVUpLbr\nWBRTBF7l0sZ7paXZsVYOu/QAJI1jPRNF3lFUxMDSE8eGx+/oUmomtl+NfCi/FEJ5\nFCU4pF1FQNmVo885HGe9Tx7UywgaXRvAGJZlA4WVie4d5Jhj8LjZRhSH8+uDgdGX\ngc/4GI8U831oQ2lHsrtYIHHNzs1EG/8Ju+INdgR/Zc5SxNx/BSF8gV7kSueEd8+/\nXlobf5JZAgMBAAECggEAHRPWBOuKCx/jOnQloiyLCsUQplubu0nmxM+Br3eFptFa\n5YQ3z36cPZB2mtcc72gv61hPbgBGC0yRmBGGpfLS/2RchI4JQYHsw2dnQtPaBB7d\nSH66sTQjDjwDNqvOWwtZIj9DroQ5keK+P/dPPFJPlARuE9z8Ojt365hgIBOazGb2\ngIh9wLXrVq7Ki8OXI+/McrxkH3tDksVH2LmzKGtWBA56MRY0v9vnJFjVd+l8Q+05\nIw4lQXt55dK7EmRLIfLnawHYIvnpalCWPe6uAmCTeoOuGASLFJJR2uzcOW9IxM0a\nMkR2dduu5vQl/ahJwxZ2cH40QJUdy7ECQg5QG4qL1wKBgQDugyaPEdoUCGC6MUas\nFR4kwDIkHj/UkgzYtsemmGG0rXCqVtIerPd6FvtKlN8BDzQbyqCaw/pDUqjFoGXN\nW969vkN5Uj9YaQ5qV8c9WLbCcMw9gT6rvqyC8b8FgwaWMKHx7TgI/8xXQ666XqpT\nMTAfINWWei0e/Scqqu6hw0v+UwKBgQDHF5ce9y9mHdVb8B7m0Oz4QIHksktKfoQa\nLoGS601zK6Rr6GeEHb03s4KLG5q9L/o9HUTXqyKERnofdEdfsGsnrKbz2Wsnr8Mk\nGwnNcPTvI3uYkeTBS4paNUxZyGVbxDOrRbBYukgwacaUIGbZ5+we1BxlVN04+l5W\nvAlNEvlfIwKBgBWMcdJhOYOv0hVgWFM5wTRuzNjohrnMzC5ULSuG/uTU+qXZHDi7\nRcyZAPEXDCLLXdjY8LOq2xR0Bl18hVYNY81ewDfYz3JMY4oGDjEjr7dXe4xe/euE\nWY+nCawUz2aIVElINlTRz4Ne0Q1zeg30FrXpQILM3QC8vGolcVPaEiaTAoGBALj7\nNjJTQPsEZSUTKeMT49mVNhsjfcktW9hntYSolEGaHx8TxHqAlzqV04kkkNWPKlZ2\nR2yLWXrFcNqg02AZLraiOE0BigpJyGpXpPf5J9q5gTD0/TKL2XSPaO1SwLpOxiMw\nkPUfv8sbvKIMqQN19XF/axLLkvBJ0DWOaKXwJzs5AoGAbO2BfPYQke9K1UhvX4Y5\nbpj6gMzaz/aeWKoC1KHijEZrY3P58I1Tt1JtZUAR+TtjpIiDY5D2etVLaLeL0K0p\nrti40epyx1RGo76MI01w+rgeZ95rmkUb9BJ3bG5WBrbrvMIHPnU+q6XOqrBij3pF\nWQAQ7pYkm/VubZlsFDMvMuA=\n-----END PRIVATE KEY-----\n",
      "client_email": "googlesheetsarvin@xenon-point-351408.iam.gserviceaccount.com",
      "client_id": "108653350174528163497",
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token",
      "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
      "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/googlesheetsarvin%40xenon-point-351408.iam.gserviceaccount.com"
    }
    
    gsheet_key = key
    gc = gspread.service_account_from_dict(credentials)
    sh = gc.open_by_key(gsheet_key)
    
    new_sheet_name = datetime.strftime(phtime.localize(datetime.today()),"%B_%d")
    r,c = df.shape
    
    try:
        sh.add_worksheet(title=new_sheet_name,rows = r+1, cols = c+1)
        worksheet = sh.worksheet(new_sheet_name)
    except:
        worksheet = sh.worksheet(new_sheet_name)
        worksheet.clear()
    worksheet.update([df.columns.tolist()]+df.values.tolist())

site_last_page = {'autodeal': {'url': 'https://www.autodeal.com.ph/used-cars/search/certified-pre-owned+repossessed+used-car-status/page-1?sort-by=relevance',
                               'xpath': '//a[@class="darklink paginator-page"]'},
                  'automart': {'url': 'https://automart.ph/all',
                               'xpath': '//a[@role="button"]'}}

if __name__ == '__main__':
    st.title('Carmax Competitor Product Scraper')
    st.markdown('''
                This app collects product info from CarMmax and other competitor platforms.
                ''')
    while True:
        # driver_path = os.getcwd() + '\\chromedriver'
        # driver = Chrome(driver_path, options=options)
        driver = Chrome(options=options)
        df_ad = autodeal_scrape(driver)
        
        st.write('AutoDeal product scraper')
        show_table(df_ad)
        
        st.write('Found {} Autodeal cars for sale.'.format(len(df_ad)))
        
        st.download_button(
            label ="Download Autodeal table",
            data = convert_csv(df_ad),
            file_name = "autodeal_prices.csv",
            key='download-autodeal-csv'
            )
        
        
        st.write('Automart product scraper')
        df_am = automart_scrape(driver)
        show_table(df_am)
        st.write('Found {} Automart cars for sale.'.format(len(df_am)))
        st.download_button(
            label ="Download Automart table",
            data = convert_csv(df_am),
            file_name = "automart_prices.csv",
            key='download-automart-csv'
            )
        
        st.write('Carmudi product scraper')
        carmudi_data = carmudi_scrape(driver)
        df_cm = carmudi_dataframe(carmudi_data)
        show_table(df_cm)
        st.write('Found {} Carmudi cars for sale.'.format(len(df_cm)))
        
        st.download_button(
            label ="Download Carmudi table",
            data = convert_csv(df_cm),
            file_name = "carmudi_prices.csv",
            key='download-carmudi-csv'
            )
        
        df_merged = pd.concat([df_ad, df_am, df_cm], axis=0)
        # write to gsheet
        write_to_gsheet(df_merged.fillna(''), "1-vHbqVXA40iQ_7Rwg14wB6C7ZMQYgAJZjpG_PzuCE5U")
        
        