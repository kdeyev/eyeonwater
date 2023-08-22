# Home Assistant integration for EyeOnWater service

1. Follow [instruction](https://hacs.xyz/docs/faq/custom_repositories/) for adding a custom git repository to your HA.

Add `https://github.com/kdeyev/eyeonwater` as Repository and select the "Integration" category.

![add-repository](https://github.com/kdeyev/eyeonwater/blob/master/img/add-repository.png?raw=true)

2. Add EyeOnWater integration following [HACS instructions](https://github.com/hacs/integration)

Follow the configuration dialog:
- Choose EyeOnWater hostname (choose eyeonwater.com unless you are in Canada).
- Choose the measurement system you prefer to use. "Imperial" will create a water sensor counting gallons, "Metric" will create a water sensor counting cubic meters.
- Use your username and password, which you use to log in on eyeonwater.com

![configuration](https://github.com/kdeyev/eyeonwater/blob/master/img/configuration.png?raw=true)

3. After successful initialization you should see the integration card appear:

![integration-card](https://github.com/kdeyev/eyeonwater/blob/master/img/integration-card.png?raw=true)

![watermeter](https://github.com/kdeyev/eyeonwater/blob/master/img/watermeter.png?raw=true)

![watermeter-graph](https://github.com/kdeyev/eyeonwater/blob/master/img/watermeter-graph.png?raw=true)

4. Got to Setting->Dashboards->Energy configuration.

You should be able to choose your water meter in the Water Consumption

![water-consumption-configuration](https://github.com/kdeyev/eyeonwater/blob/master/img/water-consumption-configuration.png?raw=true)
![water-consumption](https://github.com/kdeyev/eyeonwater/blob/master/img/water-consumption.png?raw=true)

5. Have fun and watch your utilities in the Energy Dashboard.

![energy-dashboard](https://github.com/kdeyev/eyeonwater/blob/master/img/energy-dashboard.png?raw=true)

Pay attention that EyeOnWater publishes the meter reading once in several hours (even when they accumulate the meter reading once in several minutes). So data may come with a delay of several hours.


# Unsupported state class

Please pay attention: If you look at the "Developer Tools -> Statistics", you will see an error message associated with the water sensor:
```
The state class '' of this entity is not supported.
```
or
```
Unsupported state class
The state class of this entity, is not supported.
Statistics cannot be generated until this entity has a supported state class.

If this state class was provided by an integration, this is a bug. Please report an issue.

If you have set this state class yourself, please correct it. The different state classes and when to use which can be found in the developer documentation. If the state class has permanently changed, you may want to remove the long term statistics of it from your database.

Do you want to permanently remove the long term statistics of sensor.water_meter_200010108 from your database?
```

It's a side-effect of the way we prevent the HA from recalculating the sensor statistics. You can find more information [here](https://github.com/kdeyev/eyeonwater/issues/30)
