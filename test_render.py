import sys, os
sys.path.insert(0, '.')
from app import app

os.makedirs('uploads/test_client', exist_ok=True)
with open('uploads/test_client/test.csv', 'w') as f:
    f.write('a,b,c\n1,2,3\n4,5,6\n')

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user_id'] = 'test_client'
        sess['_fresh'] = True
    resp = client.get('/dashboard/test.csv')
    print('Status:', resp.status_code)
    if resp.status_code == 302:
        print('Redirected:', resp.location)
    else:
        html = resp.data.decode('utf-8')
        print('HTML length:', len(html))
        for key in ['panel-stdnum','panel-convdt','panel-stdcat','panel-fixinc','standardize_numeric','convert_dtypes']:
            found = key in html
            print(f'  {key}: {"YES" if found else "NO"}')
