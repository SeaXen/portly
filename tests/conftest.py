import os

# Set testing environment variable early before any app imports
os.environ["PORTLY_TESTING"] = "1"
os.environ["PORTLY_DATA_DIR"] = os.path.join(os.path.dirname(__file__), "test_data_dir")
