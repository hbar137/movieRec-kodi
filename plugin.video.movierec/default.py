# movieRec Kodi add-on entry point.
import sys
from resources.lib import router

if __name__ == "__main__":
    router.dispatch(sys.argv)
