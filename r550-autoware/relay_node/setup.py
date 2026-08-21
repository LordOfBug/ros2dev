from setuptools import setup

package_name = 'r550_autoware_relay'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/relay_launch.py']),
        ('share/' + package_name + '/config', ['config/relay_topics.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='dev',
    maintainer_email='dev@todo.todo',
    description='Relay node for r550-autoware: bridges sensor/control topics between robot and remote Autoware host.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'relay_node = r550_autoware_relay.relay_node:main',
        ],
    },
)
