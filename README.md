# SMS Proxy

SMS Proxy is a microservice that allows you to proxy SMS messages between two recipients using a Flowroute TN as the intermediary layer.  The two participants of a session both send SMS messages to the same TN and are able to receive those messages on their own devices, never exposing either recipients true phone number.  

The service uses a SQLite backend and exposes multiple API resources which allows for interaction with the microservice using three standard HTTP API methods: **POST**, **GET**, and **DELETE**.

## (/) resource
* **POST** handles the incoming messages received from Flowroute.  This is the endpoint that you would set your callback URL to in your Flowroute API settings in Flowroute Manager.

## (/tn) resource
* **POST** adds a TN to your pool of virtual TNs.  
```$ curl -H "Content-Type: application/json" -X POST -d '{"value":"1NPANXXXXXX"}' https://yourdomain.com/tn```

	**Sample Response**

	```{"message": "successfully added TN to pool", "value": "1NPANXXXXXXX"}```

* **GET** retrieves your entire virtual TN pool.  
```$ curl -H "Content-Type: application/json" -X GET https://yourdomain.com/tn```

	**Sample Response**
	
	```{"available": 0, "virtual_tns": [{"session_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "value": "1NPANXXXXXX"}], "in_use": 1, "pool_size": 1}```

* **DELETE** removes a TN from your pool of virtual TNs.  
```$ curl -H "Content-Type: application/json" -X DELETE -d '{"value":"12062992129"}' https://yourdomain.com/tn```

	**Sample Response**

	```{"message": "successfully removed TN from pool", "value": "1NPANXXXXXXX"}```

## (/session) resource
* **POST** starts a new session between **participant\_a** and **participant\_b**.  Optional: expiry window, given in minutes of when a session should auto-expire.  If this option is not provided, the session will not end until a request using the DELETE method is sent.  
```$ curl -H "Content-Type: application/json" -X POST -d '{"participant_a":"1NPANXXXXX1", "participant_b":"1NPANXXXXX2", "expiry_window": 10}' https://yourdomain.com/session```

	**Sample Response**

	```{"virtual_tn": "1NPANXXXXXX", "session_id": "366910827c8e4a6593943a28e4931668", "expiry_date": "2016-05-19 22:19:58", "participant_b": "12065551213", "message": "created session", "participant_a": "12065551212"}```

* **GET**  lists all in-progress sessions.  
```$ curl -H "Content-Type: application/json" -X GET https://yourdomain.com/session```

	**Sample Response**

	```{"total_sessions": 1, "sessions": [{"virtual_tn": "1NPANXXXXXX", "expiry_date": "2016-05-19 22:19:58", "participant_b": "12065551212", "date_created": "2016-05-19 22:09:58", "participant_a": "12065551213", "id": "366910827c8e4a6593943a28e4931668"}]}```

* **DELETE** ends the specified session.  
$ curl -H "Content-Type: application/json" -X DELETE -d ```'{"session_id":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}' https://yourdomain.com/session```

	**Sample Response**

	```{"message": "successfully ended session", "session_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}```


## Before you deploy SMS Proxy

You will need your Access Key, Secret Key, and one or more SMS-enabled Flowroute number. If you do not know your Flowroute information:

* Your Access Key and Secret Key can be found on the <a href="https://manage.flowroute.com/accounts/preferences/api/" target="_blank">API Control</a> page on the Flowroute portal.
* Your Flowroute phone numbers can be found on the <a href="https://manage.flowroute.com/accounts/dids/" target="_blank">DIDs</a> page on the Flowroute portal.


##Run `git clone` and create a credentials.py file

1.  If needed, create a parent directory where you want to deploy SMS Proxy.

2.  Change to the parent directory, and run the following:

        git clone **GITHUB URL HERE**

    The `git clone` command clones the **sms-proxy** repository as a sub directory within the parent folder.

4.  Create a **credentials.py** file that includes your Flowroute credentials. 
    This is done to help protect against committing private information to a remote repository. 

    * Using a code text editor — for example, **Sublime Text** — add the following lines to a new file, replacing the Access Key and Secret Key with the information from your Flowroute account.

            FLOWROUTE_ACCESS_KEY = "Your Access Key"
            FLOWROUTE_SECRET_KEY = "Your Secret Key"

    *   Save the file as **credentials.py** in the **sms\_proxy_service directory**.

5.  Deploy the service.

## Deploy SMS Proxy Authorization

Deploying the service can be done by either building and running a Docker container as specified by the provided **Dockerfile**, or by running the application locally with Flask's built-in web server. You can first run the application in test mode before running in production mode. 

>**Note:** During development DEBUG\_MODE should be set to `True` to use the auto-generated test database. Testing can be performed on this database, which drops data in the tables each time the test module is run. Once the development cycle is over, set DEBUG\_MODE to `False` in order to use the production database. Tests cannot be run when the production database is active.

##### To run the application using Docker:  

1.  Run the following at the project's top level to build the service:

        $ docker build -t sms_proxy:0.0.1 .

    `-t` tags the image, allowing you to reference it by name instead of by image ID.

2. Next, run the following:

        $ docker run -p 8000:8000 sms_proxy:0.0.1

    `-p` binds the container port to the Docker host port. When using a virtualization layer, such as Docker-machine, the API should now be exposed on that host — for example, `http://192.168.99.100:8000`.

    By default, the `run` command spawns four Gunicorn workers listening on port `8000`. To modify the `run` command, edit the settings in the Docker **entry** file located in the project root.

##### To run the application locally:

1.  From your **sms_proxy** directory, run:

        pip install -r requirements.txt

2.  Run the following to install the service dependencies at the root level of the project:

        pip install .
        
3.  Finally, run:

        python -m sms_proxy.api

    The service is set up at the root level.

>**Note:** See the <a href="http://flask.pocoo.org/" target="_blank">Flask</a> documentation for more information about the web framework.


## Configure SMS Proxy

With the service now deployed, configure authorization settings by customizing**settings.py**

### settings.py

**settings.py** allows you to customize your organization's name and special messages around sessions.

##### To configure the settings:

1. In the **sms\_proxy_service** directory, open **settings.py**.

2. Modify any of the following values as needed:

        ORG_NAME = os.environ.get('ORG_NAME', 'Your Org Name')
        SESSION_START_MSG = "Your new session has started, send a message!"
        SESSION_END_MSG = "This session has ended, talk to you again soon!"
        NO_SESSION_MSG = "An active session was not found. Please contact support@flowroute.com"

    ###### settings.py parameters

    | Variable |  Data type   |Description                                                                                   |
    |-----------|----------|----------|------------------------------|
    |`ORG_NAME`| String    | Sets your organization's name for use in system-generated SMS messages| 
    |`SESSION_START_MSG`| String| The message that is sent to both participants when their session has been created|
    |`SESSION_END_MSG`|String| The message that is sent to both participants when their session has been terminated (via the `DELETE` method).  This message is not sent when the session is expired. |
    |`NO_SESSION_MSG`|String|The message that is sent to a user who sends a message to a virtual TN that 1) is assigned to a session to which the user does not belong or 2) is not assigned to any active session.|

3. Save the file.

## Test it! 
    
In a test environment, invoke the `docker run` command with the `test` argument to run tests and see results. To change the `docker run` command options, modify the `test`, `coverage`, or `serve` options in the `entry` script located in the top level **sms-verification** directory. 

>**Note:** To learn more about Docker entry points, see <a href="https://docs.docker.com/engine/userguide/eng-image/dockerfile_best-practices/" target="_blank"> Dockerfile Best Practices</a>.

*   Run the following:

        $ docker run -p 8000:8000 sms_proxy:0.0.1 test

    A `py.test` command is invoked from within the container. When running `coverage`, a cov-report directory is created that contains an **index.html** file detailing test coverage results.

## Add virtual TNs and start a session

Once the application is up-and-running, you can begin adding one or more virtual TNs and creating sessions.

### Add a virtual TN (POST)

Add a virtual TN to your pool. You can:

* use a curl **POST** command:

        ```$ curl -H "Content-Type: application/json" -X POST -d '{"value":"1NPANXXXXXX"}' https://yourdomain.com/tn```

    | Key: Argument | Required | Constraint |
    |-----------|----------|---------------------------------------------------------------|
|`value: virtual_tn`|Yes|`virtual_tn`is the telephone number that is used during a session.  Participants send and receive their messages from this TN when it is in use during a session.  Virtual TNs must be phone numbers that you have purchased from Flowroute.  |

    >**Important:** When using the **POST** method with JSON you must also include the complete `Content-Type:application/json" localhost:8000` header.

### Start a session (POST)

* use a curl **POST** command:

	```$ curl -H "Content-Type: application/json" -X POST -d '{"participant_a":"1NPANXXXXX1", "participant_b":"1NPANXXXXX2", "expiry_window": 10}' https://yourdomain.com/session```

    | Key: Argument | Required | Constraint |
    |-----------|----------|---------------------------------------------------------------|
|`participant_a: phone_number`|Yes|`participant_a` is a 11 digit telephone number (1NPANXXXXXX) of the first participant in a session  |
|`participant_b: phone_number`|Yes|`participant_b` is a 11 digit telephone number (1NPANXXXXXX) of the second participant in a session  |
|`expiry_window: integer`|No|`expiry_window` is the number of minutes the session should be active.  Any messages received after this window will cause the session to be ended.  Participants will receive a system-generated SMS message indicating that the session has ended.  Subsequent messages will trigger the `NO_SESSION_MSG` from settings.py. |
                
The following then occurs:

1.  A virtual TN is selected at random from the pool.  If no virtual TNs are available, `{"message": "Could not create session -- No virtual TNs available"}` is sent returned.

2.  A session is created between the two participants using an available virtual TN from the pool.  

3.  The proxy will relay messages sent to the virtual TN for the number of minutes specified in `expiry_window` if set, otherwise the session will persist indefinitely (until the session is ended via a `DELETE`request against the session endpoint.
	
	3a. To end a session:
	```$ curl -H "Content-Type: application/json" -X DELETE -d '{"session_id":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx}' https://yourdomain.com/session```

    | Key: Argument | Required | Constraint |
    |-----------|----------|---------------------------------------------------------------|
|`session_id: string`|Yes|`session_id` is a 32 character session identifier  |

## Contributing
1. Fork it!
2. Create your feature branch: `git checkout -b my-new-feature`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin my-new-feature`
5. Submit a pull request :D
