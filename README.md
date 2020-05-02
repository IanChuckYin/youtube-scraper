# youtube-scraper
YouTube scraper

Packages to install:
1. pandas
2. selenium
3. beautifulsoup4
4. requests (you probably already have this by default)

Pandas:
- https://docs.continuum.io/anaconda/install/windows/
- The best way to install pandas is through Anaconda (since it also installs all of its dependencies)
- You'd have to configure Anaconda as your default Python (the link will show you)

Selenium:
- pip install selenium

BeautifulSoup4:
- pip install beautifulsoup4


If you find that the script is crashing because your Chrome version outdates selenium's web driver version, you can upgrade chromedriver. On Mac, this would be something like:

brew cask upgrade chromedriver

In general you can just run:

npm install chromedriver
