from setuptools import find_packages, setup

package_name = "starter_lab"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="IsaacLabStarterLab contributors",
    maintainer_email="maintainers@example.invalid",
    description="ROS 2 wrappers for the IsaacLabStarterLab perception and control modules.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "perception_node = starter_lab.perception_node:main",
            "controller_node = starter_lab.controller_node:main",
        ],
    },
)
