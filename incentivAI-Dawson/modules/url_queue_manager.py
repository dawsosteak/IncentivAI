class URLQueueManager:
    def __init__(self):
        self.urls = []

    def add_urls(self, urls):
        self.urls.extend(urls)

    def get_next_url(self):
        if self.urls:
            return self.urls.pop(0)
        return None
