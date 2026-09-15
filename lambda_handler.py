from mangum import Mangum

from adapter.app import app

handler = Mangum(app)
