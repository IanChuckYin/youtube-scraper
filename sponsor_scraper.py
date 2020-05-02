import sys
import requests
import pandas as pd
import time
import math
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

'''
YouTubeChannelScraper
- When this script is run, it will prompt the user to enter the name of a YouTube channel
- You can search for a channel just like how you would in YouTube's search bar (therefore it's not case sensitive and doesn't have to be an exact match)
- The script will go into the channel's videos and grab all links in the description, excluding links in LINKS_TO_EXCLUDE
- It will then export a CSV containing the Video Title, URL Name, and the URL Link
- If you've previously searched for this channel, and have a CSV already existing for it, the script will UPDATE that CSV with new videos that the channel uploaded
'''

class YouTubeChannelScraper:
    def __init__(self, links_to_exclude, extensions, delay, limit):
        self.found_channel_name = None
        self.driver = None
        self.existing_csv_df = None
        
        if (limit is None):
            limit = math.inf
        self.LIMIT = limit
        self.LINKS_TO_EXCLUDE = links_to_exclude
        self.EXTENSIONS = extensions
        self.DELAY = delay
        self.YOUTUBE = 'https://www.youtube.com'
        
    # Prompt the user to input a search for a YouTube channel, and then launch Chrome to find that channel
    def prompt_channel_search(self):
        user_input = input('Enter a Youtube channel: ')
        searched_channel_name = '+'.join(user_input.split(' '))
        url = self.YOUTUBE + '/results?search_query=' + searched_channel_name
        driver = webdriver.Chrome()
        driver.get(url)
        try:
            self.driver = driver
            channel_link = driver.find_element_by_id('channel-title')
            self.found_channel_name = channel_link.text
            print('Found channel: ' + self.found_channel_name)
            channel_link.click()
        except Exception as e:
            print('ERROR: Could not find channel from search: ' + user_input)
            driver.quit()
            sys.exit()

    # If we have scraped this channel before, get the CSV that was previously generated and update it
    def find_existing_csv(self):
        mode = ''
        try:
            existing_csv = pd.read_csv(self.found_channel_name +'.csv', encoding='utf-8-sig')
            print('Found an existing CSV for channel: ' + self.found_channel_name)
            mode = 'UPDATE'
            self.existing_csv_df = existing_csv
        except Exception as e:
            print('Did not find an existing CSV for channel: ' + self.found_channel_name)
            mode = 'CREATE'
        print('>>> ' + mode + ' CSV INITIATED <<<')

    # Grab all videos from the channel
    def get_videos(self):
        self.driver.get(self.driver.current_url + '/videos')
        current_videos_in_dom = 0
        video_links = []
        
        # If we already hae an existing CSV of this channel, just update the CSV by adding the new videos
        if (self.existing_csv_df is not None):
            print('Grabbing NEW videos...')
            videos = self.driver.find_elements_by_id('video-title')
            video_titles = [video.text for video in videos]
            
            last_scraped_video = self.existing_csv_df['Video Title'].tolist()[0]
            
            # If our last scraped video is the first video on the channel, abort the script. CSV is already up to date
            if (last_scraped_video == video_titles[0]):
                print('Found no new videos! CSV is already up to date.')
                self.driver.quit()
                sys.exit()
            
            # If our last scraped video is not in our current list of videos (AKA a lot of newly uploaded videos),
            # keep scrolling until we find the last scraped video
            while (last_scraped_video not in video_titles or len(videos) <= self.LIMIT):
                self._scroll_page()
                videos = self.driver.find_elements_by_id('video-title')
                video_titles = [video.text for video in videos]                
            
            # Return all the videos up until our last scraped video (all new uploads)
            new_video_titles = video_titles[:video_titles.index(last_scraped_video)]
            filtered_video_objects = list(filter(lambda video : video.text in new_video_titles, videos))
            video_links = [video.get_attribute('href') for video in filtered_video_objects]
            print('New videos found: ' + str(len(video_links)))
        # If we didn't previously create a CSV from the searched channel, go through all their videos
        else:
            print('Grabbing videos...')
            # Scroll through the videos tab
            while (True):
                self._scroll_page()
                total_videos_in_channel = len(self.driver.find_elements_by_id('video-title'))
                if total_videos_in_channel == current_videos_in_dom or total_videos_in_channel >= self.LIMIT:
                    break
                current_videos_in_dom = total_videos_in_channel
            
            # Grab and store all the URLs from the videos we've found 
            videos = self.driver.find_elements_by_id('video-title')
            video_links = [video.get_attribute('href') for video in videos]
            print('Total videos found: ' + str(len(video_links)))
        
        # If a LIMIT was set, get only the videos up to the LIMIT number
        if (self.LIMIT < math.inf):
            video_links = video_links[:self.LIMIT]
            print('Limit set to: ' + str(self.LIMIT))
        return video_links
    
    # Scrape the descriptions of each video and return the data
    def scrape_video_data(self, video_links):
        csv_data = []
        wait = WebDriverWait(self.driver, 10)
        links_to_exclude = self._generate_restricted_links(self.EXTENSIONS)
        session = requests.Session()
        
        # From the list of videos that we found on the channel, go through each one and scrape their descriptions
        for video_link in video_links:
            self.driver.get(video_link)
            current_video_url = self.driver.current_url
            
            # Try finding the SHOW MORE button. If it exists, click it to expand the description
            try:
                show_more_button = wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'more-button')))
                show_more_button.click()
            except TimeoutException as e:
                print('Could not find the "SHOW MORE" button')
            
            try:
                # Get all links from the description in the current DOM
                current_page_dom = self._get_current_page_dom()
                all_links = self._get_links_from_description(current_page_dom)
                video_title = current_page_dom.find('h1', {'class': 'title'}).text

                # Filter out all timestamps if its a timestamp of the same video as well as hashtags
                filtered_list = self._filter_timestamps_and_hashtags(all_links, current_video_url)

                # Filter out all links that are included in the LINKS_TO_EXCLUDE
                filtered_list = self._filter_links(filtered_list, links_to_exclude)               

                # Iterate through our filtered list
                for link in filtered_list:
                    video_info = {}
                    url_name = link.text
                    url_link = link['href']

                    # From this filtered list, convert any tinyurls to their original URLs
                    if ('http' in link.text and '...' not in link.text):
                        url_name = self._get_original_url(session, link)
    
                    # After converting all tinyurls to their original url,
                    # do a second filter to remove links that were in LINKS_TO_EXCLUDE but were converted into tinyurls
                    if (not any(media in url_name for media in links_to_exclude)):
                        video_info['Video Title'] = video_title
                        video_info['URL Name'] = url_name
                        video_info['URL Link'] = self.YOUTUBE + url_link
                        
                        csv_data.append(video_info)

                print('(' + str(video_links.index(video_link) + 1) + '/' + str(len(video_links)) + ') - ' + video_title)
            except Exception as e:
                print('FAILED TO SCRAPE VIDEO: ' + video_title)
                print(e)
        
        return csv_data

    # Export the scraped data into a CSV, and then quit Chrome
    def export_csv(self, csv_data):
        print('Building CSV...')
        new_csv = pd.DataFrame(csv_data)
        
        # If we already have a CSV from this channel, concatenate the new data with the existing CSV data
        if (self.existing_csv_df is not None):
            new_csv = pd.concat([new_csv, self.existing_csv_df])
        
        # If there was data, add the columns
        if (len(csv_data) != 0):
            new_csv = new_csv[['Video Title', 'URL Name', 'URL Link']]
        else:
            print('No Data was found!')
        new_csv.to_csv(self.found_channel_name + '.csv', encoding='utf-8-sig', index=False)
        print('CSV exported: ' + self.found_channel_name + '.csv')
        self.driver.quit()
    
    # Scroll to the bottom the of the page
    def _scroll_page(self):
        self.driver.find_element_by_tag_name('body').send_keys(Keys.END)
        time.sleep(self.DELAY)        
    
    # Get all links from the description box
    def _get_links_from_description(self, current_page_dom):
        descrption_container = current_page_dom.find('div', {'id': 'description'})
        try:
            all_links = descrption_container.find_all('a', href=True)
        except Exception as e:
            print('Could not find any links in the description!')
            all_links = []
        return all_links
    
    # Return the HTML of the current page
    def _get_current_page_dom(self):
        return BeautifulSoup(self.driver.page_source, features='html.parser')
    
    # Return a list of all links to be excluded with '.com' appended
    def _generate_restricted_links(self, extensions):
        restricted_links = []
        for extension in extensions:
            restricted_links += list(map(lambda video : video + extension, self.LINKS_TO_EXCLUDE))
        return restricted_links
    
    # Return if the given link is a timestamp of the same video or a hashtag
    def _is_timestamp_or_hashtag(self, link, current_video_url):
        return (self.YOUTUBE + link['href'].split('&')[0] == current_video_url) or link.text[0] == '#'

    # Filters out a list of links relative to the LINKS_TO_EXCLUDE
    def _filter_links(self, links, links_to_exclude):
        return list(filter(lambda link : not any(media in link for media in links_to_exclude), links))

    # Filters out all timestamps and hashtags
    def _filter_timestamps_and_hashtags(self, links, current_video_url):
        return list(filter(lambda link : not self._is_timestamp_or_hashtag(link, current_video_url), links))

    # Convert any tinyurls to its original url
    def _get_original_url(self, session, link):
        try:
            resp = session.head(link.text, allow_redirects=True)
            return resp.url
        except Exception as e:
            print('WARNING: Unable to decode: ' + link.text + ', reverting to encoded link')
            return link.text

# Below are modifiable variables that you can tweak (in case I missed some websites that you want to exclude)
# DELAY:                    The time in seconds to wait for videos to load when scrolling down the videos tab. If your internet connection is slow, you may need to increase this value
# LIMIT:                    The maximum number of videos that you want to scrape. Default set to None, so it will scrape all videos of the channel. Otherwise you can set a number
# LINKS_TO_EXCLUDE:         The list of links that you want to exclude from the CSV
# EXTENSIONS:               The list of extensions for links that you want to exclude
DELAY = 2.5
LIMIT = 3
LINKS_TO_EXCLUDE = [
    'facebook', 
    'instagram', 
    'twitter', 
    'youtube', 
    'weibo', 
    'whatsapp', 
    'patreon', 
    'wechat', 
    'tumblr', 
    'snapchat',
    'reddit',
    'linkedin',
    'bilibili',
    'discordapp',
    'twitch', 
    'amazon',
    'docs.google',
    'tiktok'
]
EXTENSIONS = ['.com', '.tv', '.ca']

# Initialize our scraper
scraper = YouTubeChannelScraper(links_to_exclude=LINKS_TO_EXCLUDE,
                                extensions=EXTENSIONS,
                                delay=DELAY,
                                limit=LIMIT)

scraper.prompt_channel_search()
scraper.find_existing_csv()
videos = scraper.get_videos()
csv_data = scraper.scrape_video_data(videos)
scraper.export_csv(csv_data)