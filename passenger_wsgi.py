# import sys
# import os

# # Project base directory
# project_home = '/home/meherinm/inventory'

# # Add project to system path
# if project_home not in sys.path:
#     sys.path.insert(0, project_home)

# os.environ['DJANGO_SETTINGS_MODULE'] = 'inventory_api.settings'

# from django.core.wsgi import get_wsgi_application
# application = get_wsgi_application()
import sys
import os

# Project base directory
project_home = '/home/meherinm/inventoryapp'

# Add project to system path
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ['DJANGO_SETTINGS_MODULE'] = 'inventory_api.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
