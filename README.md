# SMS Proxy

SMS Proxy is a microservice that allows you to proxy SMS messages between two recipients using a Flowroute TN (telephone number) as the intermediary layer.  The two participants of a session both send SMS messages to the same TN and are able to receive those messages on their own devices, never exposing either recipient's actual phone number.  

The service uses a SQLite backend and exposes multiple API resources; this allows for interaction with the microservice using three standard HTTP API methods: **POST**, **GET**, and **DELETE**.

## Before you deploy SMS Proxy

You must have the following before you can deploy SMS Proxy.

### Have your API credentials

You will need your Access Key, Secret Key. This information can be found on the <a href="https://manage.flowroute.com/accounts/preferences/api/" target="_blank">API Control</a> page on the Flowroute portal.

### Know your Flowroute phone number

To create a proxy session, you will need one or more Flowroute phone numbers, which will be added into your TN pool. If you do not know your phone number, or if you need to verify whether or not it is enabled for SMS, you can find it on the [DIDs](https://manage.flowroute.com/accounts/dids/) page of the Flowroute portal.  The SMS proxy has a 1-to-1 mapping of number to session; the more numbers you add to your pool, the more simultaneous sessions you can create.

##Run `git clone` and create a credentials.py file

1.  If needed, create a parent directory where you want to deploy SMS Proxy.

2.  Change to the parent directory, and run the following:

        git clone https://github.com/flowroute/sms-proxy.git

    The `git clone` command clones the **sms-proxy** repository as a sub directory within the parent folder.

3.  Open up and edit **settings.py** file.  In this file you need to set your API credentials. You may configure variables here that are used by the application, or alternatively these settings may be passed in as environment variables when you deploy the service.

4.  Deploy the service.

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

With the service now deployed, configure message settings by customizing **settings.py**, allows you to customize session parameters, such as start and end messages, or organization name.

##### To configure message settings:

1. In the **sms\_proxy** directory, open **settings.py** using a code text editor.

2. Modify any of the following values as needed:

        ORG_NAME = os.environ.get('ORG_NAME', 'Your Org Name')
		SESSION_START_MSG = os.environ.get('SESSION_START_MSG', 'Your new session has started, send a message!')
		SESSION_END_MSG = os.environ.get('SESSION_END_MSG', 'This session has ended, talk to you again soon!')
		NO_SESSION_MSG = os.environ.get('NO_SESSION_MSG', 'An active session was not found. Please contact support@yourorg.com')

    The following fields can be modified in **settings.py**:

    | Variable |  Required| Data type   |Description                 |
    |-----------|----------|----------|------------------------------|
    |`ORG_NAME`| True|string    | Sets your organization's name for use in system-generated SMS messages. If the `ORG_NAME` variable is not changed, `Your Org Name` is used as the default.| 
    |`SESSION_START_MSG`|True |string| The message that is sent to both participants when their session has been created.|
    |`SESSION_END_MSG`| True |string| The message sent to both participants when a session has been terminated using the `DELETE` method.  This message is not sent for an expired session. |
    |`NO_SESSION_MSG`| True |string|The message sent to a user who sends a message to a virtual TN that 1) is assigned to a session to which the user does not belong or 2) is not assigned to any active session.|

3. Save the file.

## Test it! 
    
In a test environment, invoke the `docker run` command with the `test` argument to run tests and see results. To change the `docker run` command options, modify the `test`, `coverage`, or `serve` options in the `entry` script located in the top-level **sms-proxy** directory. 

>**Note:** To learn more about Docker entry points, see <a href="https://docs.docker.com/engine/userguide/eng-image/dockerfile_best-practices/" target="_blank"> Dockerfile Best Practices</a>.

*   Run the following:

        $ docker run -p 8000:8000 sms_proxy:0.0.1 test

    A `py.test` command is invoked from within the container. When running `coverage`, a cov-report directory is created that contains an **index.html** file detailing test coverage results.

## Add virtual TNs and start a session<a name=startsession></a>

Once the application is up-and-running, you can begin adding one or more virtual TNs and creating sessions.


See [Exposed HTTP Resources](#urlresources) for the exposed HTTP resources. 

### Add a virtual TN (POST)

*	To add a virtual TN to your pool, use a `curl POST` command, as shown in the following example:

		$ curl -H "Content-Type: application/json" -X POST -d '{"value":"1XXXXXXXXXX"}' https://MyDockerHostIP/tn

    | Key: Argument | Required | Data type |Constraint |
    |-----------|----------|----------------|-----------------------------------------------|
|`value: virtual_tn`|True| integer |The 11-digit telephone number used during a session.  Participants send and receive their messages from this TN when it is in use during a session.  Virtual TNs must be phone numbers that you have purchased from Flowroute.  |
|`https://MyDockerHostIP` | True | string| The HTTP or HTTPS endpoint where the service is located. The URL path is the IP address of the service. When using a virtualization layer, such as Docker-machine, the API should be exposed on that host — for example, `http://192.168.99.100:8000`.    |

    >**Important:** When using the **POST** method with JSON you must also include the complete `Content-Type:application/json" localhost:8000` header.

### Start a session (POST)

* To start a session, use a `curl POST` command, as shown in the following example:

		$ curl -H "Content-Type: application/json" -X POST -d '{"participant_a":"1XXXXXXXXXX", "participant_b":"1XXXXXXXXXX", "expiry_window": 10}' https://MyDockerHostIP/session

	The statement takes the following arguments:
	
    | Key: Argument | Required | Data type | Constraint |
    |-----------|----------|-----|---------------------------------------------------|
|`participant_a: phone_number`|True| string |The telephone number of the first  participant in a session, using an 11-digit E.164 1XXXXXXXXXX format. |
|`participant_b: phone_number`|True| string |The telephone number of the second participant in a session, using an 11-digit E.164 1XXXXXXXXXX format. |
|`expiry_window`|False| integer |The number of minutes the session should be active.  Any messages received after this time will end the session.  Participants will receive a system-generated SMS message indicating that the session has ended.  Subsequent messages will trigger a `NO_SESSION_MSG` from **settings.py**. |
|`https://MyDockerHostIP` | True | string| The HTTP or HTTPS endpoint where the service is located. The URL path is the IP address of the service. When using a virtualization layer, such as Docker-machine, the API should be exposed on that host — for example, `http://192.168.99.100:8000`.    |
                
The following then occurs:

1.  A virtual TN is selected at random from the pool.  If no virtual TNs are available, the following message is returned:

		{"message": "Could not create session -- No virtual TNs available"}

2.  A session is created between the two participants using an available virtual TN from the pool.  

3.  The proxy will relay messages sent to the virtual TN for the number of minutes specified in `expiry_window` if set; otherwise, the session will persist indefinitely or until the session is ended through a `DELETE`request against the session endpoint.
	
	
**To end a session:**

*	Run the following to end a session:

		$ curl -H "Content-Type: application/json" -X DELETE -d '{"session_id":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx}' https://yourdomain.com/session

	The statement takes the following arguments:
	
    | Key: Argument | Required | Data type| Constraint |
    |-----------|----------|-----------|----------------------------------------------------|
	|`session_id`|True | string| A 32-character alphanumeric session identifier. |
	|`https://MyDockerHostIP` | True | string| The HTTP or HTTPS endpoint where the service is located. The URL path is the IP address of the service. When using a virtualization layer, such as Docker-machine, the API should be exposed on that host — for example, `http://192.168.99.100:8000`.    |
	
##Exposed HTTP Resources<a name=urlresources></a>

The following URL resources are supported for the endpoints. The following examples show **POST**, **GET**, and **DELETE** HTTP methods for the applicable URL resource.

See [Add virtual TNs and start a session](#startsession) for descriptions of the fields passed in the request.

### / 
* **POST** handles the incoming messages received from Flowroute.  **`/`** is the endpoint that sets the callback URL to the URL set in your Flowroute Manager API settings.

### **`/tn`**
* **POST** adds a TN to your pool of virtual TNs.

	**Sample request**
	
	```$ curl -H "Content-Type: application/json" -X POST -d '{"value":"12062992129"}' https://yourdomain.com/tn```

	**Sample response**

		{"message": "successfully added TN to pool", "value": "12062992129"}

* **GET** retrieves your entire virtual TN pool.  

	**Sample request**
	
		$ curl -H "Content-Type: application/json" -X GET https://yourdomain.com/tn

	**Sample response**
		
		{"available": 0, "in_use": 1, "pool_size": 1, "virtual_tns": [{"session_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "value": "12062992129"}]}

	| Key: Argument | Description |
    |-----------|------------------------------------------------------|
	|`available` | The number of virtual TNs that are unreserved.|
	|`in_use`| The number of pool sessions currently being used. |
	|`pool_size` | The number of virtual TNs, both reserved and unreserved.|


* **DELETE** removes a TN from your pool of virtual TNs. 

	 
		$ curl -H "Content-Type: application/json" -X DELETE -d '{"value":"12062992129"}' https://yourdomain.com/tn

	**Sample response**

		{"message": "successfully removed TN from pool", "value": "12062992129"}

### `/session`
* **POST** starts a new session between **participant\_a** and **participant\_b**.  An optional expiration time, in minutes, can be passed indicating when a session should expire. If not passed, the session will not end until a **DELETE** request is sent. The following examples shows a **POST** request setting an expiration time of `10` minutes:

		$ curl -H "Content-Type: application/json" -X POST -d '{"participant_a":"1XXXXXXXXXX", "participant_b":"1XXXXXXXXXX", "expiry_window": 10}' https://yourdomain.com/session

	**Sample Response**

	A response message is returned indicating a successful POST for the expiration time:

	```{"virtual_tn": "1XXXXXXXXXX", "session_id": "366910827c8e4a6593943a28e4931668", "expiry_date": "2016-05-19 22:19:58", "participant_b": "12065551213", "message": "created session", "participant_a": "12065551212"}```

* **GET**  lists all in-progress sessions. 
 
		$ curl -H "Content-Type: application/json" -X GET https://yourdomain.com/session

	**Sample Response**

	```{"total_sessions": 1, "sessions": [{"virtual_tn": "1XXXXXXXXXX", "expiry_date": "2016-05-19 22:19:58", "participant_b": "12065551212", "date_created": "2016-05-19 22:09:58", "participant_a": "12065551213", "id": "366910827c8e4a6593943a28e4931668"}]}```

* **DELETE** ends the specified session.  

		$ curl -H "Content-Type: application/json" -X DELETE -d '{"session_id":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}' https://MyDockerHostIP/session

	**Sample Response**

	```{"message": "successfully ended session", "session_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}```



## Contributing
1. Fork it!
2. Create your feature branch: `git checkout -b my-new-feature`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin my-new-feature`
5. Submit a pull request :D
